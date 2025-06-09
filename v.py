import io
import lldb
import debugger
import base64
import matplotlib
import time
matplotlib.use('agg')
import matplotlib.pyplot as plt

def show_pixmap(pixmap, column=2):
    import numpy as np

    target = lldb.debugger.GetSelectedTarget()

    pixmap_name = pixmap.unwrap(pixmap).GetName()
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
    document = '<html><img src="data:image/png;base64,%s"></html>' % base64.b64encode(image_bytes.getvalue()).decode('utf-8')
    debugger.create_webview(document, view_column=column)


    return str(image_array.shape)

# index = 0
value_to_webview_map = dict()

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
            @keyframes flashFade {
                0% { background-color: #ff6b6b; }
                100% { background-color: transparent; }
            }
        </style>
        <script>
        var globalDetailStates = {};
        var currentStorageKey = '';
        var previousData = {};
        
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
            
            var nodeId = ('node_' + path + '_' + name).replace(/[ .]/g, '_');
            
            var html = '<div class="node" data-path="' + path + '" data-value="' + stringRepr + '"><strong>' + name + '</strong>: <span class="value-span">' + stringRepr + '</span>';
            
            if (children.length > 0) {
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
        
        function checkForChanges(data, path = "") {
            var changed = [];
            
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
                if (previousData[currentStorageKey] && previousData[currentStorageKey][key] !== undefined && previousData[currentStorageKey][key] !== stringRepr) {
                    changed.push(currentPath);
                }
                if (!previousData[currentStorageKey]) previousData[currentStorageKey] = {};
                previousData[currentStorageKey][key] = stringRepr;
                
                var children = currentData.children || [];
                for (var i = 0; i < children.length; i++) {
                    traverse(children[i], currentPath + '_' + i);
                }
            }
            
            traverse(data, path);
            return changed;
        }
        
        function flashElements(changedPaths) {
            // Filter out parent paths if their children are also changing and visible
            var filteredPaths = changedPaths.filter(function(path) {
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
            if (globalDetailStates[currentStorageKey]) {
                var states = globalDetailStates[currentStorageKey];
                var details = document.querySelectorAll('details');
                details.forEach(function(detail) {
                    if (detail.id && states.hasOwnProperty(detail.id)) {
                        detail.open = states[detail.id];
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
            var changedPaths = checkForChanges(data);
            var contentDiv = document.getElementById('content');
            contentDiv.innerHTML = buildHtmlFromData(data);
            restoreState();
            attachToggleListeners();
            if (changedPaths.length > 0) {
                flashElements(changedPaths);
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

def string_vis(value):
    import json
    
    global value_to_webview_map
    dbg_value = value_to_dict(value)
    val_name = value.unwrap(value).GetName()
    
    if val_name in value_to_webview_map:
        webview = value_to_webview_map[val_name]
        # Send data via postMessage
        message = {
            'type': 'updateData',
            'data': dbg_value,
            'storageKey': f'detailsState_{val_name}'
        }
        webview.post_message(json.dumps(message))
    else:
        # Create new webview with constant HTML template
        webview = debugger.create_webview(get_constant_html_template(), view_column=2, enable_scripts=True)
        value_to_webview_map[val_name] = webview
        
        # Send initial data
        message = {
            'type': 'updateData',
            'data': dbg_value,
            'storageKey': f'detailsState_{val_name}'
        }
        webview.post_message(json.dumps(message))

    return str(value)

def list_vis(value):
    import json
    
    global value_to_webview_map
    
    target = lldb.debugger.GetSelectedTarget()
    process = target.GetProcess()
    thread = process.GetSelectedThread()
    frame = thread.GetSelectedFrame()

    unwrapped = value.unwrap(value)
    variable_name = unwrapped.GetName()

    list_size = frame.EvaluateExpression(f"{variable_name}.size()").GetValueAsUnsigned()
    
    # Create dictionary structure for the list
    list_data = {
        'name': variable_name,
        'string_repr': f"size={list_size}",
        'children': []
    }
    
    # Add each list element as a child
    for i in range(list_size):
        item = frame.EvaluateExpression(f"{variable_name}[{i}]")
        item_wrapped = type(value)(item)
        child_data = value_to_dict(item_wrapped)
        # Override name to show index
        if isinstance(child_data, dict):
            child_data['name'] = f"[{i}]"
        else:
            # If value_to_dict returned a string (error), create proper structure
            child_data = {
                'name': f"[{i}]",
                'string_repr': str(item),
                'children': []
            }
        list_data['children'].append(child_data)
    
    if variable_name in value_to_webview_map:
        webview = value_to_webview_map[variable_name]
        # Send data via postMessage
        message = {
            'type': 'updateData',
            'data': list_data,
            'storageKey': f'detailsState_{variable_name}'
        }
        webview.post_message(json.dumps(message))
    else:
        # Create new webview with constant HTML template
        webview = debugger.create_webview(get_constant_html_template(), view_column=2, enable_scripts=True)
        value_to_webview_map[variable_name] = webview
        
        # Send initial data
        message = {
            'type': 'updateData',
            'data': list_data,
            'storageKey': f'detailsState_{variable_name}'
        }
        webview.post_message(json.dumps(message))

    return f"List visualization created (size: {list_size})"
