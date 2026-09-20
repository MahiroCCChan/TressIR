# TressIR

**TressIR 是一个面向 Blender、用于 LLM 辅助风格化发型建模的结构化中间表示（IR）与确定性几何工具链。**

它不要求通用 LLM 直接操纵大量 mesh vertex，而是让模型或人描述更有语义的结构：轮廓、深度场、厚度、局部 ridge、分件身份与显式叠压关系，再由确定性的几何后端生成可编辑 Blender 几何。

> 当前公开版本：**0.1.0**。几何后端已经可用；稳定的“单张 2D 图 → 高质量完整 3D 发型结构”仍是未解决的研究问题。

## 核心边界

TressIR 当前不宣称是通用单图 3D 重建模型，不宣称能自动完成整头发型，也不把有限采样的 overlap 检查包装成全局无穿模证明。

图像输入中的深度是设计估计；从已有 3D mesh 测量得到的深度会单独记录来源，两者不混为一谈。

## 快速加载

第一次使用建议直接按 [QUICKSTART.md](QUICKSTART.md) 跑内置合成示例，不需要任何私有角色资产。

在 Blender Python Console：

```python
import runpy
runpy.run_path(r"/path/to/TressIR/scripts/register_local.py")
```

面板位置：

```text
3D View → N → Hair Tools
```

构建安装 ZIP：

```bash
python scripts/build_addon_zip.py
```

Blender 5.2 中可在 **Preferences → Add-ons → Install from Disk** 选择该 ZIP；安装后还需要勾选启用 **TressIR Hair Tools**。

兼容性说明：公开 Python 包名为 `tressir_tools`。已有 `sword06c.*` 数据 schema 与 `s06c_*` Blender 序列化字段会继续保留，以兼容预发布阶段已有资产；它们不再代表公开项目品牌。

更多内容请看英文主 README 与 `docs/`。

## 开源状态

当前 release candidate 刻意不包含私有研究历史、第三方角色模型、纹理以及内部 relay 配置。

代码采用 **MIT License**。
