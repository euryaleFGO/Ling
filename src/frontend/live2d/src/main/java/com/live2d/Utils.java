package com.live2d;

import java.io.*;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * 工具类
 */
public class Utils {
    
    /**
     * 读取文件为字节数组
     */
    public static byte[] loadFile(String filePath) throws IOException {
        return Files.readAllBytes(Path.of(filePath));
    }
    
    /**
     * 从资源路径加载文件
     */
    public static byte[] loadResource(String resourcePath) throws IOException {
        InputStream is = Utils.class.getClassLoader().getResourceAsStream(resourcePath);
        if (is == null) {
            throw new FileNotFoundException("Resource not found: " + resourcePath);
        }
        
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        byte[] data = new byte[8192];
        int nRead;
        while ((nRead = is.read(data, 0, data.length)) != -1) {
            buffer.write(data, 0, nRead);
        }
        return buffer.toByteArray();
    }
    
    /**
     * 从资源路径加载文件为字节缓冲区
     */
    public static ByteBuffer loadResourceAsBuffer(String resourcePath) throws IOException {
        byte[] data = loadResource(resourcePath);
        ByteBuffer buffer = ByteBuffer.allocateDirect(data.length);
        buffer.order(ByteOrder.nativeOrder());
        buffer.put(data);
        buffer.flip();
        return buffer;
    }
    
    /**
     * 检查文件是否存在
     */
    public static boolean fileExists(String filePath) {
        return Files.exists(Path.of(filePath));
    }
}
