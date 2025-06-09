
# CodeLLDB Visualizers

Some visualizer utils for [codelldb](https://github.com/vadimcn/codelldb). Allows visualizing deep properties within lists. For example, `lv($list, "$.someprop")` displays the value of `someprop` for each element in the list. You can also chain or call methods, for example, `lv($list, "$.prop1.prop2.method()")` shows the result of calling `method` on `prop1.prop2` of every element in the list.


https://github.com/user-attachments/assets/1756cd5a-02e3-418c-884e-0f85b8e2aa14


# Setup

Here is an example setup in `launch.json`:

```
    {
      "type": "lldb",
      "request": "launch",
      "name": "Launch (lldb)",
      "stopOnEntry": false,
      "program": "${workspaceFolder}/path/to/program",
      "args": [],
      "cwd": "${workspaceFolder}",
      "preLaunchTask": "build",
      "initCommands": [
        "command script import /path/to/codelldb_vis/codelldb_visualizers.py",
        "script from codelldb_visualizers import list_vis as lv", // alias so we don't have to type codelldb_visualizers.list_vis every time
      ],
      "preRunCommands": [
        "breakpoint name configure --disable cpp_exception"
      ],
    },
```

# Usage
In the watch window add something like: `/py lv($list, "$.prop")`. The `/py` tells codelldb to evaluate the following as a python expression. `lv` is the alias defined in the `launch.json` for `codelldb_visualizers.list_vis`. `$list` is the name of the `c++` list variable that you want to inspect with a `$` prefix (the variables in c++ are also defined in `codelldb`'s python side but with a `$` prefix). And `"$.prop"` is the expression that you want to evaluate for each element of the list (`$` is replaced with each element in the list).