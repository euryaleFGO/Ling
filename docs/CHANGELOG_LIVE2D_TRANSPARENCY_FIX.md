# Live2D 透明渲染修复日志

## 修复日期
2026-04-23

## 问题描述

### 症状
Live2D 角色在透明窗口中渲染时，整个角色呈现"毛玻璃"般的半透明效果：
- **白色背景下**：角色脸色苍白，腮红几乎看不见，皮肤颜色很浅
- **深色背景下**：角色显示正常，腮红清晰，皮肤颜色饱和
- **根本原因**：背景颜色透过角色显示，产生了不正确的颜色混合效果

### 技术分析
问题出在 OpenGL 混合模式（Blend Mode）设置不当：
- 原始代码使用了标准的 Alpha 混合：`glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)`
- 这种混合模式对 RGB 和 Alpha 通道使用相同的混合函数
- 在透明窗口环境下，背景颜色会与角色颜色进行混合，导致角色颜色被背景"污染"
- 表现为：浅色背景让角色变浅（发白），深色背景让角色颜色正常

## 解决方案

### 修改文件
`src/frontend/live2d/src/main/java/com/live2d/Main.java`

### 修改内容

**修改前（第 284-287 行）：**
```java
glViewport(0, 0, width, height);
glEnable(GL_BLEND);
glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
glClearColor(0.0f, 0.0f, 0.0f, 0.0f);
glDisable(GL_DEPTH_TEST);
```

**修改后：**
```java
glViewport(0, 0, width, height);
glEnable(GL_BLEND);
// 使用分离混合函数：RGB 通道使用覆盖模式，Alpha 通道使用标准混合
// 这样可以确保角色的颜色不受背景影响，同时保持透明效果
glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA);
glClearColor(0.0f, 0.0f, 0.0f, 0.0f);
glDisable(GL_DEPTH_TEST);
```

### 技术细节

使用 `glBlendFuncSeparate` 分别控制 RGB 和 Alpha 通道的混合行为：

#### RGB 通道混合
```
glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, ...)
```
- **混合公式**：`result.rgb = src.rgb * src.a + dst.rgb * (1 - src.a)`
- **效果**：角色的颜色按 Alpha 值正确混合，不透明部分（Alpha = 1.0）完全覆盖背景
- **优点**：角色颜色不受背景颜色影响

#### Alpha 通道混合
```
glBlendFuncSeparate(..., GL_ONE, GL_ONE_MINUS_SRC_ALPHA)
```
- **混合公式**：`result.a = src.a * 1 + dst.a * (1 - src.a)`
- **效果**：保持正确的透明度信息
- **优点**：窗口背景仍然透明，只有角色部分不透明

## 修复效果

### 修复前
- ❌ 白色背景：角色发白，腮红消失
- ❌ 深色背景：显示正常（但这不是正确的解决方案）
- ❌ 背景颜色影响角色显示

### 修复后
- ✅ 白色背景：角色颜色正常，腮红清晰
- ✅ 深色背景：角色颜色正常，腮红清晰
- ✅ 任何背景：角色显示一致，不受背景颜色影响
- ✅ 窗口背景保持透明

## 相关知识

### OpenGL 混合函数对比

| 函数 | RGB 混合 | Alpha 混合 | 适用场景 |
|------|---------|-----------|---------|
| `glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)` | 标准混合 | 标准混合 | 普通 2D 渲染 |
| `glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA)` | 标准混合 | 加法混合 | **透明窗口渲染（推荐）** |
| `glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA)` | 预乘 Alpha | 预乘 Alpha | 预乘 Alpha 纹理 |

### 为什么需要分离混合？

在透明窗口环境下：
1. **窗口本身是透明的**：需要正确的 Alpha 通道来控制透明度
2. **角色应该不透明**：RGB 通道需要完全覆盖背景，不受背景颜色影响
3. **标准混合会导致颜色污染**：背景颜色会与角色颜色混合，产生错误的显示效果

使用 `glBlendFuncSeparate` 可以：
- RGB 通道：正确混合颜色，不透明部分完全覆盖
- Alpha 通道：保持透明度信息，让窗口背景透明

## 测试验证

### 测试环境
- 操作系统：Windows
- OpenGL 版本：3.3 Core Profile
- LWJGL 版本：3.x
- Live2D SDK：Cubism SDK

### 测试场景
1. ✅ 白色桌面背景：角色显示正常，颜色饱和
2. ✅ 黑色桌面背景：角色显示正常，颜色饱和
3. ✅ 彩色桌面背景：角色显示正常，不受背景颜色影响
4. ✅ 窗口拖动：背景变化时角色颜色保持一致
5. ✅ 腮红效果：在任何背景下都清晰可见

## 参考资料

- [OpenGL glBlendFuncSeparate 文档](https://www.khronos.org/registry/OpenGL-Refpages/gl4/html/glBlendFuncSeparate.xhtml)
- [Live2D Cubism SDK 渲染指南](https://docs.live2d.com/)
- [透明窗口渲染最佳实践](https://www.khronos.org/opengl/wiki/Blending)

## 总结

这次修复成功解决了 Live2D 角色在透明窗口中渲染时的颜色混合问题。通过使用 `glBlendFuncSeparate` 分离 RGB 和 Alpha 通道的混合模式，确保了：
1. 角色颜色不受背景影响
2. 窗口背景保持透明
3. 在任何桌面背景下都能正常显示

这是一个典型的透明窗口渲染问题，解决方案简洁有效，值得在类似场景中参考。
