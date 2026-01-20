package com.live2d.platform;

import com.sun.jna.Native;
import com.sun.jna.Pointer;
import com.sun.jna.platform.win32.User32;
import com.sun.jna.platform.win32.WinDef;
import com.sun.jna.win32.W32APIOptions;

/**
 * Windows 透明窗口支持 - 使用 DWM API 强制启用透明
 * 
 * 解决 NVIDIA Optimus 显卡 GLFW 透明窗口黑屏问题
 */
public class WindowsTransparency {
    
    public interface User32Ex extends User32 {
        User32Ex INSTANCE = Native.load("user32", User32Ex.class, W32APIOptions.DEFAULT_OPTIONS);
        boolean SetLayeredWindowAttributes(WinDef.HWND hwnd, int crKey, byte bAlpha, int dwFlags);
    }
    
    public interface Dwmapi extends com.sun.jna.Library {
        Dwmapi INSTANCE = Native.load("dwmapi", Dwmapi.class);
        int DwmExtendFrameIntoClientArea(WinDef.HWND hwnd, MARGINS pMarInset);
        int DwmEnableBlurBehindWindow(WinDef.HWND hwnd, DWM_BLURBEHIND pBlurBehind);
    }
    
    public static class MARGINS extends com.sun.jna.Structure {
        public int cxLeftWidth;
        public int cxRightWidth;
        public int cyTopHeight;
        public int cyBottomHeight;
        
        @Override
        protected java.util.List<String> getFieldOrder() {
            return java.util.Arrays.asList("cxLeftWidth", "cxRightWidth", "cyTopHeight", "cyBottomHeight");
        }
    }
    
    public static class DWM_BLURBEHIND extends com.sun.jna.Structure {
        public int dwFlags;
        public boolean fEnable;
        public WinDef.HRGN hRgnBlur;
        public boolean fTransitionOnMaximized;
        
        @Override
        protected java.util.List<String> getFieldOrder() {
            return java.util.Arrays.asList("dwFlags", "fEnable", "hRgnBlur", "fTransitionOnMaximized");
        }
    }
    
    private static final int GWL_EXSTYLE = -20;
    private static final int WS_EX_LAYERED = 0x00080000;
    private static final int LWA_ALPHA = 0x00000002;
    private static final int DWM_BB_ENABLE = 0x00000001;
    
    /**
     * 为窗口启用透明支持
     */
    public static boolean enableTransparency(long hwndPointer) {
        try {
            WinDef.HWND hwnd = new WinDef.HWND(Pointer.createConstant(hwndPointer));
            
            System.out.println("🔧 正在配置 Windows 透明窗口...");
            
            // 设置分层窗口样式
            int exStyle = User32.INSTANCE.GetWindowLong(hwnd, GWL_EXSTYLE);
            if (User32.INSTANCE.SetWindowLong(hwnd, GWL_EXSTYLE, exStyle | WS_EX_LAYERED) == 0) {
                System.err.println("  ❌ 设置 WS_EX_LAYERED 失败");
                return false;
            }
            System.out.println("  ✓ WS_EX_LAYERED 已设置");
            
            // 设置窗口透明属性
            if (!User32Ex.INSTANCE.SetLayeredWindowAttributes(hwnd, 0, (byte) 255, LWA_ALPHA)) {
                System.err.println("  ❌ SetLayeredWindowAttributes 失败");
                return false;
            }
            System.out.println("  ✓ SetLayeredWindowAttributes 已设置");
            
            // DWM 扩展帧到客户区
            MARGINS margins = new MARGINS();
            margins.cxLeftWidth = -1;
            margins.cxRightWidth = -1;
            margins.cyTopHeight = -1;
            margins.cyBottomHeight = -1;
            
            int result = Dwmapi.INSTANCE.DwmExtendFrameIntoClientArea(hwnd, margins);
            if (result != 0) {
                System.err.println("  ⚠ DwmExtendFrameIntoClientArea 失败 (错误码: " + result + ")");
            } else {
                System.out.println("  ✓ DWM 帧扩展已启用");
            }
            
            // 启用 DWM 模糊效果
            try {
                DWM_BLURBEHIND blurBehind = new DWM_BLURBEHIND();
                blurBehind.dwFlags = DWM_BB_ENABLE;
                blurBehind.fEnable = true;
                blurBehind.hRgnBlur = null;
                blurBehind.fTransitionOnMaximized = false;
                
                Dwmapi.INSTANCE.DwmEnableBlurBehindWindow(hwnd, blurBehind);
                System.out.println("  ✓ DWM 模糊效果已启用");
            } catch (Exception e) {
                // 忽略
            }
            
            System.out.println("✅ Windows 透明窗口配置完成！");
            return true;
            
        } catch (Exception e) {
            System.err.println("❌ 启用透明窗口失败: " + e.getMessage());
            return false;
        }
    }
}
