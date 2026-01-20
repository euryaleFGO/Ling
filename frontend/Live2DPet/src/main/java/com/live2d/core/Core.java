package com.live2d.core;

import com.live2d.Utils;
import com.sun.jna.Memory;
import com.sun.jna.Native;
import com.sun.jna.Pointer;
import com.sun.jna.ptr.FloatByReference;

import java.io.IOException;

/**
 * Live2D 核心功能封装
 */
public class Core {
    private Pointer model;
    private Pointer moc;
    private Memory mocMemory;
    private Memory modelMemory;
    private boolean initialized;
    
    private static final int CSM_ALIGNOF_MOC = 64;
    private static final int CSM_ALIGNOF_MODEL = 16;
    
    public Core() {
        this.initialized = false;
    }
    
    /**
     * 初始化模型
     */
    public boolean initializeModel(String mocPath) {
        try {
            byte[] mocData;
            
            if (mocPath.startsWith("/")) {
                String resourcePath = mocPath.substring(1);
                mocData = Utils.loadResource(resourcePath);
            } else if (Utils.fileExists(mocPath)) {
                mocData = Utils.loadFile(mocPath);
            } else {
                mocData = Utils.loadResource(mocPath);
            }
            
            if (mocData == null || mocData.length == 0) {
                System.err.println("Failed to load MOC data from: " + mocPath);
                return false;
            }
            
            System.out.println("Loading MOC file: " + mocPath);
            System.out.println("  MOC size: " + mocData.length + " bytes");
            
            // 分配对齐的 MOC 内存
            int mocSize = mocData.length;
            int extraSpace = CSM_ALIGNOF_MOC;
            mocMemory = new Memory(mocSize + extraSpace);
            
            mocMemory.write(0, mocData, 0, mocSize);
            moc = mocMemory;
            
            // 尝试恢复 MOC
            Pointer revivedMoc = null;
            boolean success = false;
            
            for (int offset = 0; offset < CSM_ALIGNOF_MOC && offset + mocSize <= mocSize + extraSpace; offset += 8) {
                mocMemory.write(offset, mocData, 0, mocSize);
                moc = mocMemory.share(offset);
                revivedMoc = CubismCore.INSTANCE.csmReviveMocInPlace(moc, mocSize);
                if (revivedMoc != null && revivedMoc != Pointer.NULL) {
                    moc = revivedMoc;
                    success = true;
                    break;
                }
            }
            
            if (!success || revivedMoc == null) {
                System.err.println("Failed to revive MOC file");
                return false;
            }
            
            // 获取模型大小
            int modelSize = CubismCore.INSTANCE.csmGetSizeofModel(moc);
            if (modelSize <= 0) {
                System.err.println("Failed to get model size");
                return false;
            }
            
            System.out.println("  Model size: " + modelSize + " bytes");
            
            // 分配模型内存
            int modelExtraSpace = CSM_ALIGNOF_MODEL;
            modelMemory = new Memory(modelSize + modelExtraSpace);
            model = modelMemory;
            
            // 初始化模型
            Pointer initializedModel = CubismCore.INSTANCE.csmInitializeModelInPlace(moc, model, modelSize);
            if (initializedModel == null || initializedModel == Pointer.NULL) {
                for (int offset = 0; offset < CSM_ALIGNOF_MODEL && offset + modelSize <= modelSize + modelExtraSpace; offset += 4) {
                    model = modelMemory.share(offset);
                    initializedModel = CubismCore.INSTANCE.csmInitializeModelInPlace(moc, model, modelSize);
                    if (initializedModel != null && initializedModel != Pointer.NULL) {
                        model = initializedModel;
                        break;
                    }
                }
                
                if (initializedModel == null || initializedModel == Pointer.NULL) {
                    System.err.println("Failed to initialize model");
                    return false;
                }
            } else {
                model = initializedModel;
            }
            
            this.initialized = true;
            System.out.println("Model initialized successfully!");
            System.out.println("  - Parameter count: " + getParameterCount());
            System.out.println("  - Part count: " + getPartCount());
            System.out.println("  - Drawable count: " + getDrawableCount());
            return true;
        } catch (IOException e) {
            System.err.println("Error loading MOC file: " + e.getMessage());
            return false;
        } catch (Exception e) {
            System.err.println("Error initializing model: " + e.getMessage());
            return false;
        }
    }
    
    public void dispose() {
        model = null;
        moc = null;
        if (mocMemory != null) {
            mocMemory.close();
            mocMemory = null;
        }
        if (modelMemory != null) {
            modelMemory.close();
            modelMemory = null;
        }
        this.initialized = false;
    }
    
    public void update() {
        if (initialized && model != null && model != Pointer.NULL) {
            CubismCore.INSTANCE.csmUpdateModel(model);
        }
    }
    
    public int getParameterCount() {
        if (!initialized || model == null) return 0;
        return CubismCore.INSTANCE.csmGetParameterCount(model);
    }
    
    public float getParameterValue(int parameterIndex) {
        if (!initialized || model == null) return 0.0f;
        Pointer valuesPtr = CubismCore.INSTANCE.csmGetParameterValues(model);
        if (valuesPtr == null) return 0.0f;
        return valuesPtr.getFloat(parameterIndex * 4);
    }
    
    public void setParameterValue(int parameterIndex, float value) {
        if (!initialized || model == null) return;
        Pointer valuesPtr = CubismCore.INSTANCE.csmGetParameterValues(model);
        if (valuesPtr == null) return;
        valuesPtr.setFloat(parameterIndex * 4, value);
    }
    
    public float getParameterValue(String parameterId) {
        int index = getParameterIndex(parameterId);
        if (index < 0) return 0.0f;
        return getParameterValue(index);
    }
    
    public void setParameterValue(String parameterId, float value) {
        int index = getParameterIndex(parameterId);
        if (index < 0) return;
        setParameterValue(index, value);
    }
    
    private int getParameterIndex(String parameterId) {
        if (!initialized || model == null) return -1;
        
        int count = getParameterCount();
        Pointer idsPtr = CubismCore.INSTANCE.csmGetParameterIds(model);
        if (idsPtr == null) return -1;
        
        for (int i = 0; i < count; i++) {
            Pointer stringPtr = idsPtr.getPointer(i * Native.POINTER_SIZE);
            if (stringPtr != null) {
                String id = stringPtr.getString(0);
                if (parameterId.equals(id)) {
                    return i;
                }
            }
        }
        return -1;
    }
    
    public int getPartCount() {
        if (!initialized || model == null) return 0;
        return CubismCore.INSTANCE.csmGetPartCount(model);
    }
    
    public float getPartOpacity(String partId) {
        int index = getPartIndex(partId);
        if (index < 0) return 1.0f;
        Pointer opacitiesPtr = CubismCore.INSTANCE.csmGetPartOpacities(model);
        if (opacitiesPtr == null) return 1.0f;
        return opacitiesPtr.getFloat(index * 4);
    }
    
    public void setPartOpacity(String partId, float opacity) {
        int index = getPartIndex(partId);
        if (index < 0) return;
        Pointer opacitiesPtr = CubismCore.INSTANCE.csmGetPartOpacities(model);
        if (opacitiesPtr == null) return;
        opacitiesPtr.setFloat(index * 4, opacity);
    }
    
    private int getPartIndex(String partId) {
        if (!initialized || model == null) return -1;
        
        int count = getPartCount();
        Pointer idsPtr = CubismCore.INSTANCE.csmGetPartIds(model);
        if (idsPtr == null) return -1;
        
        for (int i = 0; i < count; i++) {
            Pointer stringPtr = idsPtr.getPointer(i * Native.POINTER_SIZE);
            if (stringPtr != null) {
                String id = stringPtr.getString(0);
                if (partId.equals(id)) {
                    return i;
                }
            }
        }
        return -1;
    }
    
    public int getDrawableCount() {
        if (!initialized || model == null) return 0;
        return CubismCore.INSTANCE.csmGetDrawableCount(model);
    }
    
    public CubismCore.csmVector2[] getDrawableVertices(int drawableIndex) {
        if (!initialized || model == null) return null;
        
        int count = getDrawableCount();
        if (drawableIndex < 0 || drawableIndex >= count) return null;
        
        update();
        
        Pointer vertexCountsPtr = CubismCore.INSTANCE.csmGetDrawableVertexCounts(model);
        if (vertexCountsPtr == null) return null;
        
        int vertexCount = vertexCountsPtr.getInt(drawableIndex * 4);
        if (vertexCount <= 0) return null;
        
        Pointer vertexPositionsPtr = CubismCore.INSTANCE.csmGetDrawableVertexPositions(model);
        if (vertexPositionsPtr == null) return null;
        
        Pointer drawableVerticesPtr = vertexPositionsPtr.getPointer(drawableIndex * Native.POINTER_SIZE);
        if (drawableVerticesPtr == null) return null;
        
        CubismCore.csmVector2[] vertices = new CubismCore.csmVector2[vertexCount];
        for (int i = 0; i < vertexCount; i++) {
            CubismCore.csmVector2 v = new CubismCore.csmVector2();
            v.X = drawableVerticesPtr.getFloat(i * 8);
            v.Y = drawableVerticesPtr.getFloat(i * 8 + 4);
            vertices[i] = v;
        }
        
        return vertices;
    }
    
    public short[] getDrawableIndices(int drawableIndex) {
        if (!initialized || model == null) return null;
        
        int count = getDrawableCount();
        if (drawableIndex < 0 || drawableIndex >= count) return null;
        
        Pointer indexCountsPtr = CubismCore.INSTANCE.csmGetDrawableIndexCounts(model);
        if (indexCountsPtr == null) return null;
        
        int indexCount = indexCountsPtr.getInt(drawableIndex * 4);
        if (indexCount <= 0) return null;
        
        Pointer indicesPtr = CubismCore.INSTANCE.csmGetDrawableIndices(model);
        if (indicesPtr == null) return null;
        
        Pointer drawableIndicesPtr = indicesPtr.getPointer(drawableIndex * Native.POINTER_SIZE);
        if (drawableIndicesPtr == null) return null;
        
        short[] indices = new short[indexCount];
        for (int i = 0; i < indexCount; i++) {
            indices[i] = drawableIndicesPtr.getShort(i * 2);
        }
        
        return indices;
    }
    
    public float[] getCanvasInfo() {
        if (!initialized || model == null) {
            return new float[]{2.0f, 2.0f, 0.0f, 0.0f, 1.0f};
        }
        
        CubismCore.csmVector2 size = new CubismCore.csmVector2();
        CubismCore.csmVector2 origin = new CubismCore.csmVector2();
        FloatByReference pixelsPerUnit = new FloatByReference();
        
        CubismCore.INSTANCE.csmReadCanvasInfo(model, size, origin, pixelsPerUnit);
        
        return new float[]{
            size.X, size.Y,
            origin.X, origin.Y,
            pixelsPerUnit.getValue()
        };
    }
    
    public CubismCore.csmVector2[] getDrawableVertexUvs(int drawableIndex) {
        if (!initialized || model == null) return null;
        
        int count = getDrawableCount();
        if (drawableIndex < 0 || drawableIndex >= count) return null;
        
        Pointer vertexCountsPtr = CubismCore.INSTANCE.csmGetDrawableVertexCounts(model);
        if (vertexCountsPtr == null) return null;
        
        int vertexCount = vertexCountsPtr.getInt(drawableIndex * 4);
        if (vertexCount <= 0) return null;
        
        Pointer vertexUvsPtr = CubismCore.INSTANCE.csmGetDrawableVertexUvs(model);
        if (vertexUvsPtr == null) return null;
        
        Pointer drawableUvsPtr = vertexUvsPtr.getPointer(drawableIndex * Native.POINTER_SIZE);
        if (drawableUvsPtr == null) return null;
        
        CubismCore.csmVector2[] uvs = new CubismCore.csmVector2[vertexCount];
        for (int i = 0; i < vertexCount; i++) {
            CubismCore.csmVector2 uv = new CubismCore.csmVector2();
            uv.X = drawableUvsPtr.getFloat(i * 8);
            uv.Y = drawableUvsPtr.getFloat(i * 8 + 4);
            uvs[i] = uv;
        }
        
        return uvs;
    }
    
    public int getDrawableTextureIndex(int drawableIndex) {
        if (!initialized || model == null) return -1;
        
        int count = getDrawableCount();
        if (drawableIndex < 0 || drawableIndex >= count) return -1;
        
        Pointer textureIndicesPtr = CubismCore.INSTANCE.csmGetDrawableTextureIndices(model);
        if (textureIndicesPtr == null) return -1;
        
        return textureIndicesPtr.getInt(drawableIndex * 4);
    }
    
    public boolean isDrawableVisible(int drawableIndex) {
        if (!initialized || model == null) return false;
        
        update();
        
        Pointer flagsPtr = CubismCore.INSTANCE.csmGetDrawableDynamicFlags(model);
        if (flagsPtr == null) return true;
        
        byte flags = flagsPtr.getByte(drawableIndex);
        return (flags & 0x01) != 0;
    }
    
    public int[] getDrawableRenderOrders() {
        if (model == null) return new int[0];
        
        int count = CubismCore.INSTANCE.csmGetDrawableCount(model);
        Pointer ordersPtr = CubismCore.INSTANCE.csmGetDrawableRenderOrders(model);
        
        if (ordersPtr == null) {
            int[] defaultOrders = new int[count];
            for (int i = 0; i < count; i++) {
                defaultOrders[i] = i;
            }
            return defaultOrders;
        }
        
        return ordersPtr.getIntArray(0, count);
    }
    
    public boolean isInitialized() {
        return initialized;
    }
}
