package com.live2d;

import com.google.gson.*;
import com.live2d.core.Core;

import java.io.IOException;
import java.util.*;

/**
 * Live2D 动作播放器
 * 解析 model3.json 与 motion3.json，根据 Agent/LLM 情绪自主播放模型动作
 * 参考 AIRI 逻辑：情绪 → 动作组映射
 */
 public class MotionPlayer {
     private String modelBasePath;
    private final Map<String, List<String>> motionGroups = new HashMap<>();
    private MotionData currentMotion;
    private double motionTime;
    private boolean playing;
    private boolean loop;

    public MotionPlayer(String modelBasePath) {
        this.modelBasePath = modelBasePath.replace("\\", "/");
        if (!this.modelBasePath.endsWith("/")) {
            this.modelBasePath += "/";
        }
    }

    /**
     * 从 model3.json 加载动作组定义
     */
    public boolean loadModelConfig(String modelJsonPath) {
        try {
            String path = modelJsonPath.startsWith("/") ? modelJsonPath.substring(1) : modelJsonPath;
            if (!path.contains("/")) {
                path = modelBasePath + path;
            }
            String json = new String(Utils.loadResource(path), java.nio.charset.StandardCharsets.UTF_8);
            JsonObject root = JsonParser.parseString(json).getAsJsonObject();
            JsonObject refs = root.getAsJsonObject("FileReferences");
            if (refs == null) return false;

            JsonObject motions = refs.getAsJsonObject("Motions");
            if (motions == null) return false;

            for (String groupName : motions.keySet()) {
                JsonArray arr = motions.getAsJsonArray(groupName);
                List<String> files = new ArrayList<>();
                for (JsonElement e : arr) {
                    String file = e.getAsJsonObject().get("File").getAsString();
                    files.add(resolveMotionPath(file));
                }
                motionGroups.put(groupName, files);
            }
            System.out.println("[MotionPlayer] 已加载动作组: " + motionGroups.keySet());
            return true;
        } catch (Exception e) {
            System.err.println("[MotionPlayer] 加载 model3.json 失败: " + e.getMessage());
            return false;
        }
    }

    private String resolveMotionPath(String relPath) {
        if (relPath.startsWith("motion/")) {
            return modelBasePath + relPath;
        }
        return modelBasePath + "motion/" + relPath;
    }

    /**
     * 播放指定动作组
     * @param group 动作组名 (如 Idle, Tap@Body, Tap)
     * @param index 组内索引，默认 0
     */
    public void playMotion(String group, int index) {
        List<String> files = motionGroups.get(group);
        if (files == null || files.isEmpty()) {
            System.out.println("[MotionPlayer] 未知动作组: " + group);
            return;
        }
        int i = Math.max(0, Math.min(index, files.size() - 1));
        String path = files.get(i);
        loadAndPlay(path);
    }

    public void playMotion(String group) {
        playMotion(group, 0);
    }

    private void loadAndPlay(String motionPath) {
        try {
            String path = motionPath.startsWith("/") ? motionPath.substring(1) : motionPath;
            String json = new String(Utils.loadResource(path), java.nio.charset.StandardCharsets.UTF_8);
            currentMotion = parseMotion(json);
            motionTime = 0;
            playing = true;
            loop = currentMotion.loop;
            System.out.println("[MotionPlayer] 播放: " + motionPath + " (duration=" + currentMotion.duration + "s, loop=" + loop + ")");
        } catch (Exception e) {
            System.err.println("[MotionPlayer] 加载动作失败: " + motionPath + " - " + e.getMessage());
        }
    }

    /**
     * 每帧更新，将动作曲线应用到 Core
     */
    public void update(Core core, double deltaTime) {
        if (!playing || currentMotion == null || core == null || !core.isInitialized()) {
            return;
        }

        motionTime += deltaTime;

        if (motionTime >= currentMotion.duration) {
            if (loop) {
                motionTime = motionTime % currentMotion.duration;
            } else {
                playing = false;
                return;
            }
        }

        float t = (float) motionTime;
        for (Curve curve : currentMotion.curves) {
            if ("Parameter".equals(curve.target)) {
                // 避免覆盖口型，嘴型完全交给 ExpressionController + TTS/ASR 控制；
                // 眼睛 / 睫毛 等其它参数仍然允许随动作变化。
                if (curve.id != null && curve.id.startsWith("ParamMouth")) {
                    continue;
                }
                float value = evaluateCurve(curve, t);
                core.setParameterValue(curve.id, value);
            }
        }
    }

    public boolean isPlaying() {
        return playing;
    }

    public void stop() {
        playing = false;
        currentMotion = null;
    }

    // ----- 解析 motion3.json -----
    private static class MotionData {
        double duration;
        boolean loop;
        List<Curve> curves = new ArrayList<>();
    }

    private static class Curve {
        String target;
        String id;
        List<Segment> segments = new ArrayList<>();
    }

    private static class Segment {
        int type;  // 0=linear, 1=bezier, 2=stepped, 3=inverse-stepped
        float t0, v0;
        float t1, v1;
        float cp1v, cp2v;  // bezier control point values (t fixed by spec)
    }

    private MotionData parseMotion(String json) {
        JsonObject root = JsonParser.parseString(json).getAsJsonObject();
        JsonObject meta = root.getAsJsonObject("Meta");
        MotionData data = new MotionData();
        data.duration = meta.get("Duration").getAsDouble();
        // 为了避免 Live2D 一直循环同一个动作（导致角色永远“在动”且口型被覆盖），
        // 这里强制所有动作播放一遍后停止：由上层逻辑（情绪/事件）决定何时再次触发。
        data.loop = false;

        JsonArray curvesArr = root.getAsJsonArray("Curves");
        for (JsonElement ce : curvesArr) {
            JsonObject co = ce.getAsJsonObject();
            String target = co.get("Target").getAsString();
            String id = co.get("Id").getAsString();
            JsonArray segArr = co.getAsJsonArray("Segments");

            Curve curve = new Curve();
            curve.target = target;
            curve.id = id;

            float[] arr = new float[segArr.size()];
            for (int i = 0; i < arr.length; i++) {
                arr[i] = segArr.get(i).getAsFloat();
            }

            int i = 0;
            float lastT = 0, lastV = 0;
            while (i < arr.length) {
                int type;
                float t0, v0;
                if (curve.segments.isEmpty()) {
                    t0 = arr[i++];
                    v0 = arr[i++];
                } else {
                    t0 = lastT;
                    v0 = lastV;
                }
                if (i >= arr.length) break;
                type = (int) arr[i++];

                Segment seg = new Segment();
                seg.type = type;
                seg.t0 = t0;
                seg.v0 = v0;

                if (type == 0 || type == 2 || type == 3) {
                    if (i + 1 < arr.length) {
                        seg.t1 = arr[i++];
                        seg.v1 = arr[i++];
                        lastT = seg.t1;
                        lastV = seg.v1;
                    } else break;
                } else if (type == 1) {
                    if (i + 5 < arr.length) {
                        seg.cp1v = arr[i + 1];
                        seg.cp2v = arr[i + 3];
                        seg.t1 = arr[i + 4];
                        seg.v1 = arr[i + 5];
                        lastT = seg.t1;
                        lastV = seg.v1;
                        i += 6;
                    } else break;
                }
                curve.segments.add(seg);
            }
            data.curves.add(curve);
        }
        return data;
    }

    private float evaluateCurve(Curve curve, float t) {
        if (curve.segments.isEmpty()) return 0;
        for (Segment seg : curve.segments) {
            if (t >= seg.t0 && t <= seg.t1) {
                return evaluateSegment(seg, t);
            }
        }
        Segment last = curve.segments.get(curve.segments.size() - 1);
        return t > last.t1 ? last.v1 : curve.segments.get(0).v0;
    }

    private float evaluateSegment(Segment seg, float t) {
        switch (seg.type) {
            case 0:
                return linearInterp(seg.t0, seg.v0, seg.t1, seg.v1, t);
            case 1:
                float dt = seg.t1 - seg.t0;
                if (dt <= 0) return seg.v0;
                float s = (t - seg.t0) / dt;
                return cubicBezier(seg.v0, seg.cp1v, seg.cp2v, seg.v1, s);
            case 2:
                return seg.v0;
            case 3:
                return seg.v1;
            default:
                return linearInterp(seg.t0, seg.v0, seg.t1, seg.v1, t);
        }
    }

    private float linearInterp(float t0, float v0, float t1, float v1, float t) {
        if (t1 <= t0) return v0;
        float s = (t - t0) / (t1 - t0);
        return v0 + (v1 - v0) * s;
    }

    private float cubicBezier(float p0, float p1, float p2, float p3, float s) {
        float u = 1 - s;
        return u * u * u * p0 + 3 * u * u * s * p1 + 3 * u * s * s * p2 + s * s * s * p3;
    }

    /** 获取当前模型支持的动作组列表 */
    public Set<String> getAvailableGroups() {
        return new HashSet<>(motionGroups.keySet());
    }

    /** 获取指定动作组的动作数量（用于随机选一个 Idle 等） */
    public int getMotionCount(String group) {
        List<String> files = motionGroups.get(group);
        return files == null ? 0 : files.size();
    }
}
