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

### Live2D 窗口时间一长闪退

多半是**卡退**（崩溃），不是自动退出。常见原因：

1. **Java/OpenGL 内存或驱动**：长时间运行后显存或堆内存不足、GPU 驱动超时，导致 JVM 或原生库（`Live2DCubismCore.dll`）崩溃。
2. **未捕获异常**：例如消息轮询、纹理更新等线程里抛异常未处理，会直接导致 JVM 退出。

**如何确认原因**：主程序（main.py）已把 Live2D 的 stdout/stderr 转发到终端，闪退前或闪退瞬间会打印 `[Live2D]` 开头的错误或堆栈。若终端里没有有用信息，可到 `src/frontend/live2d` 下执行：

```bash
mvn -q -DskipTests compile exec:java
```

在弹出窗口旁保留该终端，闪退时查看终端里的 Java 异常或原生错误。

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
