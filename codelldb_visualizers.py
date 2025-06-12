import io
import lldb
import debugger
import base64
import matplotlib
import codelldb
import time
matplotlib.use('agg')
import matplotlib.pyplot as plt

type_visualizers = dict()

def show_pixmap(target, pixmap, column=2):
    import numpy as np

    # target = lldb.debugger.GetSelectedTarget()

    pixmap_name = pixmap.GetName()
    process = target.GetProcess()
    thread = process.GetSelectedThread()
    frame = thread.GetSelectedFrame()
    
    image = frame.EvaluateExpression(f"{pixmap_name}.toImage()")

    image_width = frame.EvaluateExpression(f"{image.GetName()}.width()").GetValueAsSigned()
    image_height = frame.EvaluateExpression(f"{image.GetName()}.height()").GetValueAsSigned()

    image_data = frame.EvaluateExpression(f"{image.GetName()}.constBits()").GetValueAsUnsigned()
    bytes_per_line = frame.EvaluateExpression(f"{image.GetName()}.bytesPerLine()").GetValueAsSigned()
    image_size = image_height * bytes_per_line

    memory = process.ReadMemory(image_data, image_size, lldb.SBError())

    image_array = np.frombuffer(memory, dtype=np.uint8)
    image_array = image_array.reshape((image_height, bytes_per_line // 4, 4))
    image_array = image_array[:, :, :3]

    plt.imshow(image_array)
    image_bytes = io.BytesIO()
    plt.savefig(image_bytes, format='png')
    res = '<img src="data:image/png;base64,%s">' % base64.b64encode(image_bytes.getvalue()).decode('utf-8')
    return res
    # document = '<html><img src="data:image/png;base64,%s"></html>' % base64.b64encode(image_bytes.getvalue()).decode('utf-8')
    # debugger.create_webview(document, view_column=column)


    # return str(image_array.shape)

type_visualizers['QPixmap'] = show_pixmap

# index = 0
value_to_webview_map = dict()
previous_list_sizes = dict()  # Track previous list sizes

def value_to_dict(value):
    try:
        unwrapped = value.unwrap(value)
        children_count = unwrapped.GetNumChildren()

        name = unwrapped.GetName()
        string_repr = str(value)

        resp = dict()
        resp['name'] = name
        resp['string_repr'] = string_repr
        resp['children'] = []

        for i in range(children_count):
            child = unwrapped.GetChildAtIndex(i)
            child_wrapped = type(value)(child)
            resp['children'].append(value_to_dict(child_wrapped))
        return resp
    except Exception as e:
        return str(e)

def dict_to_html(dict_data, path=""):
    """Convert a dictionary created by value_to_dict to collapsible HTML"""
    if isinstance(dict_data, str):
        return f"<span>{dict_data}</span>"
    
    if not isinstance(dict_data, dict):
        return f"<span>{str(dict_data)}</span>"
    
    name = dict_data.get('name', 'unknown')
    string_repr = dict_data.get('string_repr', '')
    children = dict_data.get('children', [])
    
    # Create unique ID for this node
    node_id = f"node_{path}_{name}".replace(" ", "_").replace(".", "_")
    
    html = f"<div><strong>{name}</strong>: {string_repr}"
    
    if children:
        html += f"""
        <details id="{node_id}" style="margin-left: 20px;">
            <summary style="cursor: pointer; color: green;">({len(children)})</summary>
            <div style="margin-left: 10px;">
        """
        for i, child in enumerate(children):
            html += dict_to_html(child, f"{path}_{i}")
        html += "</div></details>"
    
    html += "</div>"
    return html

def get_constant_html_template():
    """Returns the constant HTML template for the debugger visualizer"""
    return """
    <html>
    <head>
        <style>
            body { font-family: monospace; }
            .node { margin-bottom: 5px; }
            details { margin-left: 20px; }
            summary { cursor: pointer; color: green; }
            .children { margin-left: 10px; }
            .flash-red {
                background-color: #ff6b6b;
                animation: flashFade 1s ease-out forwards;
            }
            .flash-green {
                background-color: #4ecdc4;
                animation: flashFadeGreen 1s ease-out forwards;
            }
            @keyframes flashFade {
                0% { background-color: #ff6b6b; }
                100% { background-color: transparent; }
            }
            @keyframes flashFadeGreen {
                0% { background-color: #4ecdc4; }
                100% { background-color: transparent; }
            }
            .table-container {
                margin: 10px 0;
                overflow-x: auto;
            }
            .data-table {
                border-collapse: collapse;
                width: 100%;
                margin: 5px 0;
            }
            .data-table th, .data-table td {
                border: 1px solid #ddd;
                padding: 4px 8px;
                text-align: left;
            }
            .data-table th {
                background-color: #3a3a3a;
                font-weight: bold;
            }
            .data-table tr:nth-child(even) {
                background-color: #2a2a2a;
            }
            .filter-controls {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px 12px;
                margin: 8px 0;
                display: flex;
                align-items: center;
                gap: 8px;
                flex-wrap: wrap;
            }
            .filter-controls select.filter-column {
                padding: 4px 8px;
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: white;
                font-family: monospace;
                font-size: 12px;
                min-width: 120px;
            }
            .filter-controls input.filter-input {
                padding: 4px 8px;
                border: 1px solid #ccc;
                border-radius: 3px;
                font-family: monospace;
                font-size: 12px;
                min-width: 150px;
                flex: 1;
            }
            .filter-label {
                font-size: 12px;
                color: #666;
                font-weight: bold;
                white-space: nowrap;
            }
        </style>
        <script>
        var globalDetailStates = {};
        var currentStorageKey = '';
        var previousData = {};
        var previousListSizes = {};
        var filterSettings = {};  // store per‐table filter selections
        
        function buildHtmlFromData(data, path = "") {
            if (typeof data === 'string') {
                return '<span data-path="' + path + '" data-value="' + data + '">' + data + '</span>';
            }
            
            if (typeof data !== 'object' || data === null) {
                return '<span data-path="' + path + '" data-value="' + String(data) + '">' + String(data) + '</span>';
            }
            
            var name = data.name || 'unknown';
            var stringRepr = data.string_repr || '';
            var children = data.children || [];
            var tableData = data.table_data || null;
            
            var nodeId = ('node_' + path + '_' + name).replace(/[ .]/g, '_');
            
            var html = '<div class="node" data-path="' + path + '" data-value="' + stringRepr + '"><strong>' + name + '</strong>: <span class="value-span">' + stringRepr + '</span>';
            
            if (tableData) {
                // --- Filter controls for this table ---
                html += '<div class="filter-controls" data-path="' + path + '" style="margin-bottom:5px;">';
                html += '<select class="filter-column" onchange="applyFilter(\\'' + path + '\\', this)">';
                for (var h = 0; h < tableData.headers.length; h++) {
                    html += '<option value="' + (h+1) + '">' + tableData.headers[h] + '</option>';
                }
                html += '</select>';
                html += '<input type="text" class="filter-input" placeholder="Filter value" oninput="applyFilter(\\'' + path + '\\', this)" />';
                html += '</div>';
                html += '<div class="table-container">';
                html += '<table class="data-table">';
                
                // Header row
                html += '<tr><th>Index</th>';
                for (var i = 0; i < tableData.headers.length; i++) {
                    html += '<th>' + tableData.headers[i] + '</th>';
                }
                html += '</tr>';
                
                // Data rows
                for (var i = 0; i < tableData.rows.length; i++) {
                    var row = tableData.rows[i];
                    html += '<tr data-path="' + path + '_' + i + '"><td>' + i + '</td>';
                    for (var j = 0; j < row.length; j++) {
                        html += '<td data-path="' + path + '_' + i + '_' + j + '">' + row[j] + '</td>';
                    }
                    html += '</tr>';
                }
                html += '</table></div>';
            } else if (children.length > 0) {
                // New filter controls for non-table lists
                html += '<div class="filter-controls" data-path="' + path + '" style="margin-bottom:5px;">';
                html += '<input type="text" class="filter-input" placeholder="Filter items" oninput="applyFilter(\\'' + path + '\\', this)" />';
                html += '</div>';
                html += '<details id="' + nodeId + '">';
                html += '<summary>(' + children.length + ')</summary>';
                html += '<div class="children">';
                for (var i = 0; i < children.length; i++) {
                    html += buildHtmlFromData(children[i], path + '_' + i);
                }
                html += '</div></details>';
            }
            
            html += '</div>';
            return html;
        }
        
        // --- Client‐side filter function ---
        function applyFilter(path, element) {
            var controls = element.closest('.filter-controls');
            var filterText = controls.querySelector('input.filter-input').value;
            var container = controls.nextElementSibling;
            var table = container.querySelector('table.data-table');

            if (table) {
                var colIndex = parseInt(controls.querySelector('select.filter-column').value) + 1;
                console.log('col value:')
                console.log(controls.querySelector('select.filter-column').value);
                // remember this filter for future updates
                filterSettings[path] = { colIndex: colIndex, filterText: filterText };
                var rows = container.querySelectorAll('table.data-table tr');
                for (var i = 1; i < rows.length; i++) {
                    var cells = rows[i].querySelectorAll('td');
                    var show = false;
                    if (!filterText) {
                        show = true;
                    } else if (colIndex === -1) {
                        // any cell match
                        for (var j = 0; j < cells.length; j++) {
                            if (cells[j].textContent === filterText) { show = true; break; }
                        }
                    } else if (colIndex > 0 && colIndex <= cells.length) {
                        if (cells[colIndex - 1].textContent === filterText) show = true;
                    }
                    rows[i].style.display = show ? '' : 'none';
                }
            } else {
                // filtering for non-table children: match only the value for exact equality
                var items = container.querySelectorAll('.children .node');
                items.forEach(function(item) {
                    var valueSpan = item.querySelector('.value-span');
                    var val = valueSpan ? valueSpan.textContent : '';
                    var show = !filterText || (val === filterText);
                    item.style.display = show ? '' : 'none';
                });
            }
        }
        
        // --- reapply saved filters after re-render ---
        function reapplyFilters() {
           for (var path in filterSettings) {
               var controls = document.querySelector('.filter-controls[data-path="' + path + '"]');
               if (!controls) continue;
               var fs = filterSettings[path];
               var selectElement = controls.querySelector('select.filter-column');
               if (selectElement) {
                   selectElement.value = fs.colIndex - 1; // Convert back to 0-indexed for select options
               }
               controls.querySelector('input.filter-input').value = fs.filterText;
               applyFilter(path, controls.querySelector('input.filter-input'));
           }
        }

        function checkForChanges(data, path = "") {
            var changed = [];
            var newElements = [];
            
            function traverse(currentData, currentPath) {
                if (typeof currentData === 'string' || typeof currentData !== 'object' || currentData === null) {
                    var key = currentPath + '_value';
                    var value = String(currentData);
                    if (previousData[currentStorageKey] && previousData[currentStorageKey][key] !== undefined && previousData[currentStorageKey][key] !== value) {
                        changed.push(currentPath);
                    }
                    if (!previousData[currentStorageKey]) previousData[currentStorageKey] = {};
                    previousData[currentStorageKey][key] = value;
                    return;
                }
                
                var stringRepr = currentData.string_repr || '';
                var key = currentPath + '_repr';
                
                // Check if this is a list (has size= in string_repr)
                var isListMatch = stringRepr.match(/^size=(\d+)$/);
                if (isListMatch) {
                    var currentSize = parseInt(isListMatch[1]);
                    var sizeKey = currentPath + '_size';
                    var prevSize = previousListSizes[currentStorageKey] && previousListSizes[currentStorageKey][sizeKey];
                    
                    if (prevSize !== undefined && currentSize > prevSize) {
                        // New elements added - mark them as new
                        for (var i = prevSize; i < currentSize; i++) {
                            newElements.push(currentPath + '_' + i);
                        }
                    }
                    
                    if (!previousListSizes[currentStorageKey]) previousListSizes[currentStorageKey] = {};
                    previousListSizes[currentStorageKey][sizeKey] = currentSize;
                } else {
                    // Regular change detection for non-lists
                    if (previousData[currentStorageKey] && previousData[currentStorageKey][key] !== undefined && previousData[currentStorageKey][key] !== stringRepr) {
                        changed.push(currentPath);
                    }
                }
                
                if (!previousData[currentStorageKey]) previousData[currentStorageKey] = {};
                previousData[currentStorageKey][key] = stringRepr;
                
                var children = currentData.children || [];
                for (var i = 0; i < children.length; i++) {
                    traverse(children[i], currentPath + '_' + i);
                }
            }
            
            traverse(data, path);
            return { changed: changed, newElements: newElements };
        }
        
        function flashElements(changedPaths, newElementPaths) {
            // Flash new elements green
            newElementPaths.forEach(function(path) {
                var elements = document.querySelectorAll('[data-path="' + path + '"]');
                elements.forEach(function(element) {
                    element.classList.remove('flash-green');
                    // Force reflow to restart animation
                    element.offsetHeight;
                    element.classList.add('flash-green');
                });
            });
            
            // Flash changed elements red (excluding those that are new)
            var filteredPaths = changedPaths.filter(function(path) {
                // Don't flash if this path is a new element
                if (newElementPaths.indexOf(path) !== -1) {
                    return false;
                }
                
                // Check if any other path in the list is a child of this path
                var hasChangedChild = changedPaths.some(function(otherPath) {
                    return otherPath !== path && otherPath.startsWith(path + '_');
                });
                
                if (hasChangedChild) {
                    // Check if the parent details element is open (children are visible)
                    var parentElement = document.querySelector('[data-path="' + path + '"]');
                    if (parentElement) {
                        var detailsElement = parentElement.querySelector('details');
                        if (detailsElement && detailsElement.open) {
                            return false; // Don't flash parent if children are visible and changing
                        }
                    }
                }
                return true;
            });
            
            filteredPaths.forEach(function(path) {
                var elements = document.querySelectorAll('[data-path="' + path + '"]');
                elements.forEach(function(element) {
                    element.classList.remove('flash-red');
                    // Force reflow to restart animation
                    element.offsetHeight;
                    element.classList.add('flash-red');
                });
            });
        }
        
        function saveState() {
            var states = {};
            var details = document.querySelectorAll('details');
            details.forEach(function(detail) {
                if (detail.id) {
                    states[detail.id] = detail.open;
                }
            });
            globalDetailStates[currentStorageKey] = states;
        }
        
        function restoreState() {
            var details = document.querySelectorAll('details');
            if (globalDetailStates[currentStorageKey]) {
                var states = globalDetailStates[currentStorageKey];
                details.forEach(function(detail) {
                    if (detail.id && states.hasOwnProperty(detail.id)) {
                        detail.open = states[detail.id];
                    }
                });
            } else {
                // No previous state - expand top-level details by default
                details.forEach(function(detail) {
                    // Check if this is a top-level detail (parent is content div)
                    if (detail.parentElement && detail.parentElement.parentElement && detail.parentElement.parentElement.id === 'content') {
                        detail.open = true;
                    }
                });
            }
        }
        
        function attachToggleListeners() {
            var details = document.querySelectorAll('details');
            details.forEach(function(detail) {
                detail.addEventListener('toggle', function() {
                    saveState();
                });
            });
        }
        
        function updateContent(data, storageKey) {
            currentStorageKey = storageKey;
            var changeInfo = checkForChanges(data);
            var contentDiv = document.getElementById('content');
            contentDiv.innerHTML = buildHtmlFromData(data);
            restoreState();
            attachToggleListeners();
            reapplyFilters();  // restore filters on every update
            if (changeInfo.changed.length > 0 || changeInfo.newElements.length > 0) {
                flashElements(changeInfo.changed, changeInfo.newElements);
            }
        }
        
        // Listen for messages from the debugger
        window.addEventListener('message', function(event) {
            var message = event.data;
            var message = JSON.parse(message);
            if (message.type === 'updateData') {
                updateContent(message.data, message.storageKey);
            }
        });
        </script>
    </head>
    <body>
        <div id="content">Waiting for data...</div>
    </body>
    </html>
    """

def object_vis(value):
    import json
    
    global value_to_webview_map
    dbg_value = value_to_dict(value)
    val_name = value.unwrap(value).GetName()
    
    if val_name in value_to_webview_map:
        webview = value_to_webview_map[val_name]
        message = {
            'type': 'updateData',
            'data': dbg_value,
            'storageKey': f'detailsState_{val_name}'
        }
        webview.post_message(json.dumps(message))
    else:
        webview = debugger.create_webview(get_constant_html_template(), view_column=2, enable_scripts=True)
        value_to_webview_map[val_name] = webview
        
        message = {
            'type': 'updateData',
            'data': dbg_value,
            'storageKey': f'detailsState_{val_name}'
        }
        webview.post_message(json.dumps(message))

    return str(value)

def get_string_from_value(target, result):
    result_type = result.GetType().GetCanonicalType().GetName()

    if result_type in type_visualizers:
        return type_visualizers[result_type](target, result)
    elif result_type == 'char':
        result_numerical_value = result.GetValueAsSigned()
        result = chr(result_numerical_value)
        result_str = result
    else:
        result_wrapped = codelldb.value.Value(result)
        result_str = str(result_wrapped)
        if result_str == "":
            result_str = str(result)
            # print only the value and not the type name
            # find the first index of "=" and slice from there
            first_equal_index = result_str.find('=')
            if first_equal_index != -1:
                result_str = result_str[first_equal_index + 1:].strip()
            else:
                result_str = result_str.strip()
            
    return result_str

cached_compiled_expressions = []

# def get_list_expression_evaluator(frame, container_expr, expr):
#     global cached_compiled_expressions

#     for cached_frame, cached_container_exp, cached_expr, cached_result in cached_compiled_expressions:
#         if cached_frame == frame and cached_container_exp == container_expr.GetName() and cached_expr == expr:
#             return cached_result

#     # expr = "$[$.sizse()-1]"
#     cxx = f"""
#     []({container_expr.GetTypeName()} &c) {{
#         auto temp = {expr.replace('$', 'c[0]')};
#         using T = decltype(temp);
#         static T res[1000];

#         int max_iter = c.size() < 1000 ? c.size() : 1000;
#         for (int i = 0; i < c.size(); ++i) {{
#             res[i] = {expr.replace('$', 'c[i]')};
#         }}
#         return res;
#     }};
#     """
#     opts = lldb.SBExpressionOptions()
#     opts.SetLanguage(lldb.eLanguageTypeC_plus_plus)

#     result = frame.EvaluateExpression(cxx, opts)
#     if not result.error.Success():
#         raise RuntimeError("Failed to inject batch helper: " + result.error.GetCString())

#     cached_compiled_expressions.append((frame, container_expr.GetName(), expr, result))
#     return result

# def get_expression_string_values_for_list(target, frame, value, expression):
#     try:
#         container_size = frame.EvaluateExpression(f"{value.unwrap(value).GetName()}.size()").GetValueAsSigned()
#         evaluator_lambda = get_list_expression_evaluator(frame, value.unwrap(value), expression)
#         evaluated = frame.EvaluateExpression(f'{evaluator_lambda.GetName()}({value.unwrap(value).GetName()})')
#         ptr_type = evaluated.GetType()
#         element_type = ptr_type.GetPointeeType()
#         element_size = element_type.GetByteSize()
#         start_address = evaluated.GetValueAsUnsigned()

#         string_list = []
#         for i in range(container_size):
#             address = start_address + i * element_size
#             value_name = f'{value.unwrap(value).GetName()}[{i}]'
#             element_sbvalue = target.CreateValueFromAddress(f"{expression}", lldb.SBAddress(address, target), element_type)
#             element_string = get_string_from_value(element_sbvalue)
#             string_list.append(element_string)

#             # we can't rely on type name because it just returns "T"
#             # print(element_type.GetCanonicalType())
#             # is_type_char = # todo

#         return string_list
#     except Exception as e:
#         return str(e)

count = 0

def get_expression_string_values_for_list(target, frame, value, expression):
    global count
    count += 1
    container_size = frame.EvaluateExpression(f"{value.unwrap(value).GetName()}.size()").GetValueAsSigned()

    try:
        cxx = f"""
        auto& c = {value.unwrap(value).GetName()};
        auto& data_ptr = c.__begin_;
        auto temp = {expression.replace('$', 'data_ptr[0]')};
        using T_{count} = decltype(temp);
        static char buffer_{count}[sizeof(T_{count}) * 1000];
        T_{count}* res_{count} = (T_{count}*)((void*)&buffer_{count}[0]);

        int max_iter_{count} = c.size() < 1000 ? c.size() : 1000;
        for (int i = 0; i < max_iter_{count}; ++i) {{
            res_{count}[i] = {expression.replace('$', 'data_ptr[i]')};
        }}
        (T_{count}*)&res_{count}[0];
        """

        opts = lldb.SBExpressionOptions()
        opts.SetLanguage(lldb.eLanguageTypeC_plus_plus)
        opts.SetUnwindOnError(True)
        opts.SetIgnoreBreakpoints(True)

        evaluated = frame.EvaluateExpression(cxx)

        ptr_type = evaluated.GetType()
        element_type = ptr_type.GetPointeeType()
        element_size = element_type.GetByteSize()
        start_address = evaluated.GetValueAsUnsigned()

        string_list = []
        for i in range(container_size):
            address = start_address + i * element_size
            element_sbvalue = target.CreateValueFromAddress(f"var_{count}_{i}", lldb.SBAddress(address, target), element_type)
            element_string = get_string_from_value(target, element_sbvalue)
            string_list.append(element_string)

        return string_list
    except Exception as e:
        res = []
        for i in range(container_size):
            ith_value = target.EvaluateExpression(f"{expression.replace('$', f'{value.unwrap(value).GetName()}[{i}]')}")
            ith_string = get_string_from_value(target, ith_value)
            res.append(ith_string)
        return res

def list_vis(value, *expressions):
    import json
    
    global value_to_webview_map, previous_list_sizes
    
    target = lldb.debugger.GetSelectedTarget()
    process = target.GetProcess()
    thread = process.GetSelectedThread()
    frame = thread.GetSelectedFrame()


    unwrapped = value.unwrap(value)
    variable_name = unwrapped.GetName()

    list_size = frame.EvaluateExpression(f"{variable_name}.size()").GetValueAsUnsigned()
    
    storage_key = f'detailsState_{variable_name}'
    if storage_key not in previous_list_sizes:
        previous_list_sizes[storage_key] = {}
    
    
    list_data = {
        'name': variable_name,
        'string_repr': f"size={list_size}",
        'children': []
    }
    
    # If multiple expressions, use table format
    if len(expressions) > 1:
        table_data = {
            'headers': expressions,
            'rows': []
        }
        # Bulk evaluate each expression for all elements
        expr_values = []
        for expr in expressions:
            vals = get_expression_string_values_for_list(target, frame, value, expr)
            # if error returned as string, replicate it for each index
            expr_values.append(vals if isinstance(vals, list) else [str(vals)] * list_size)
        # Transpose into rows
        for i in range(list_size):
            row = [expr_values[j][i] for j in range(len(expressions))]
            table_data['rows'].append(row)
        list_data['table_data'] = table_data
    else:
        # Single expression or no expression - use faster bulk eval if one expression
        if expressions:
            # Bulk evaluate single expression
            vals = get_expression_string_values_for_list(target, frame, value, expressions[0])
            for i, result_str in enumerate(vals if isinstance(vals, list) else [str(vals)] * list_size):
                child_data = {
                    'name': f"[{i}]",
                    'string_repr': result_str,
                    'children': []
                }
                list_data['children'].append(child_data)
        else:
            # No expression: fallback to existing per-element dict conversion
            for i in range(list_size):
                item = frame.EvaluateExpression(f"{variable_name}[{i}]")
                item_wrapped = type(value)(item)
                child_data = value_to_dict(item_wrapped)
                if isinstance(child_data, dict):
                    child_data['name'] = f"[{i}]"
                else:
                    child_data = {
                        'name': f"[{i}]",
                        'string_repr': str(item),
                        'children': []
                    }
                list_data['children'].append(child_data)
    
    if variable_name in value_to_webview_map:
        webview = value_to_webview_map[variable_name]
        message = {
            'type': 'updateData',
            'data': list_data,
            'storageKey': f'detailsState_{variable_name}'
        }
        webview.post_message(json.dumps(message))
    else:
        webview = debugger.create_webview(get_constant_html_template(), view_column=2, enable_scripts=True)
        value_to_webview_map[variable_name] = webview
        
        message = {
            'type': 'updateData',
            'data': list_data,
            'storageKey': f'detailsState_{variable_name}'
        }
        webview.post_message(json.dumps(message))

    expression_info = f" with {len(expressions)} expressions" if expressions else ""
    return f"List visualization created (size: {list_size}){expression_info}"
