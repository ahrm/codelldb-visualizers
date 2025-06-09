
# CodeLLDB Visualizers

Some visualizer utils for codelldb. Allows visualizing deep properties within lists.

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
