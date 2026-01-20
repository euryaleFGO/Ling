# Live2D 桌面宠物

透明背景的 Live2D 桌面宠物程序，基于 LWJGL + OpenGL。

## 技术方案

- **渲染**: LWJGL 3 + OpenGL 3.3 Core Profile
- **透明**: GLFW 透明帧缓冲 + Windows DWM API
- **Live2D**: Cubism Core SDK 5-r.4.1

## 运行方式

```bash
mvn compile exec:java
```

## 注意事项

### NVIDIA Optimus 显卡透明问题

如果窗口显示黑色背景而不是透明：

1. 打开 **Windows 设置 > 显示 > 图形**
2. 添加 `java.exe`（位于 JDK 安装目录的 `bin` 文件夹）
3. 选择 **省电**（使用集成显卡）

这是 NVIDIA Optimus 驱动的已知 bug（GLFW Issue #1288），独显无法正确提供 Alpha 通道。

## 项目结构

```
Live2DPet/
├── pom.xml                     # Maven 配置
├── Live2DCubismCore.dll        # Cubism 原生库
├── src/main/java/com/live2d/
│   ├── Main.java               # 主程序
│   ├── Utils.java              # 工具类
│   ├── core/
│   │   ├── Core.java           # Cubism 核心封装
│   │   └── CubismCore.java     # JNA 接口
│   ├── model/
│   │   └── Model.java          # 模型管理
│   └── platform/
│       └── WindowsTransparency.java  # Windows 透明窗口
└── src/main/resources/res/
    └── hiyori/                 # Live2D 模型
```

## 依赖

- Java 17+
- LWJGL 3.3.3
- JNA 5.13.0
- Live2D Cubism Core SDK 5-r.4.1

## 功能

- ✅ 透明背景
- ✅ 鼠标跟随
- ✅ 眨眼动画
- ✅ 呼吸动画
- ✅ 身体摇摆
- ✅ 头发物理
- ✅ 始终置顶
