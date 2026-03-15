package com.live2d.model;

import com.live2d.Utils;
import com.live2d.core.Core;

import java.nio.ByteBuffer;

/**
 * Live2D Model Manager
 */
public class Model {
    private Core core;
    private String modelPath;
    private boolean loaded;
    
    public Model() {
        this.core = new Core();
        this.loaded = false;
    }
    
    public boolean load(String modelPath) {
        this.modelPath = modelPath;
        
        try {
            String mocPath = findMocFile(modelPath);
            if (mocPath == null) {
                System.err.println("MOC file not found in: " + modelPath);
                return false;
            }
            
            if (!core.initializeModel(mocPath)) {
                System.err.println("Failed to initialize model core");
                return false;
            }
            
            this.loaded = true;
            return true;
        } catch (Exception e) {
            System.err.println("Error loading model: " + e.getMessage());
            return false;
        }
    }
    
    private String findMocFile(String modelPath) {
        String normalizedPath = modelPath.replace("\\", "/");
        if (!normalizedPath.startsWith("/")) {
            normalizedPath = "/" + normalizedPath;
        }
        
        String[] possibleMocFiles = {
            normalizedPath + "/hiyori_free_t08.moc3",
            normalizedPath + "/model.moc3",
            normalizedPath + "/model.moc"
        };
        
        for (String resourcePath : possibleMocFiles) {
            try {
                byte[] test = Utils.loadResource(resourcePath.substring(1));
                if (test != null && test.length > 0) {
                    return resourcePath;
                }
            } catch (Exception e) {
                // continue
            }
        }
        
        String[] fileSystemPaths = {
            modelPath + "/hiyori_free_t08.moc3",
            modelPath + "/model.moc3",
            modelPath + "/model.moc"
        };
        
        for (String path : fileSystemPaths) {
            if (Utils.fileExists(path)) {
                return path;
            }
        }
        
        return null;
    }
    
    public void dispose() {
        if (core != null) {
            core.dispose();
        }
        this.loaded = false;
    }
    
    public void update() {
        if (loaded && core != null) {
            core.update();
        }
    }
    
    public void setParameterValue(String parameterId, float value) {
        if (loaded && core != null) {
            core.setParameterValue(parameterId, value);
        }
    }
    
    public float getParameterValue(String parameterId) {
        if (loaded && core != null) {
            return core.getParameterValue(parameterId);
        }
        return 0.0f;
    }
    
    public boolean isLoaded() {
        return loaded;
    }
    
    public Core getCore() {
        return core;
    }
    
    public ByteBuffer loadResourceAsBuffer(String resourcePath) {
        try {
            return Utils.loadResourceAsBuffer(resourcePath);
        } catch (Exception e) {
            System.err.println("Failed to load resource: " + resourcePath);
            return null;
        }
    }
}
