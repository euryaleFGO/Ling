# Skill Generator Tool References

## Overview

The skill generator tool allows the Agent to create new tools dynamically following OpenClaw's skill creator design principles.

## Tool Types

### 1. simple - Simple Tool
Best for: Single-purpose tools with minimal state
Example: `DateTimeTool`, `ExitAppTool`

### 2. manager - Manager Tool
Best for: Tools that manage multiple items (CRUD operations)
Example: `ReminderTool`, `ReminderManager`

### 3. file - File Operation Tool
Best for: Reading/writing files with path safety checks
Example: `FileReadTool`, `FileWriteTool`

### 4. api - API Call Tool
Best for: External service integration
Example: `BrowserSearchTool`

## Usage Examples

### Create a new tool

```
action: "create"
tool_name: "weather查询"
tool_type: "api"
description: "当用户询问天气、气温、空气质量时使用"
```

### Generate template without saving

```
action: "generate_template"
tool_name: "calculator"
tool_type: "simple"
description: "简单的计算器工具"
```

### List all available templates

```
action: "list_templates"
```

### Validate existing tool code

```
action: "validate"
code: "<tool code here>"
```

or

```
action: "validate"
filepath: "src/backend/llm/tools/my_tool.py"
```

### Get creation guide

```
action: "guide"
```

## Naming Conventions

| Element | Format | Example |
|---------|--------|---------|
| Tool name | kebab-case | `my-tool`, `file-reader` |
| Class name | PascalCase | `MyTool`, `FileReaderTool` |
| File name | snake_case + `_tool.py` | `my_tool_tool.py` |

## Required Tool Structure

Every tool must have:

1. `@property name` - Unique identifier for LLM to call
2. `@property description` - When to use this tool
3. `@property parameters` - List of `ToolParameter`
4. `execute()` method - Returns `ToolResult`

## After Creating a Tool

1. Edit the generated file to implement logic
2. Import in `tools/__init__.py`
3. Add to `__all__` list
4. Register in `Agent._setup_tools()`: `self._tool_manager.register(MyTool())`
5. Restart the agent

## Design Principles

### Concise is Key
Only add context the model doesn't already have. Keep descriptions short.

### Progressive Disclosure
- Metadata: name + description (always in context)
- SKILL.md: When skill triggers (<5k words)
- References: Loaded as needed

### Security First
- File tools MUST check `_is_safe_path()`
- Delete operations require confirmation
- API calls need timeout
