"""
中草药处方OCR识别模块
使用 RapidOCR（PaddleOCR+ONNX），纯CPU，无需额外下载模型

支持两种调用方式：
  1. 函数调用：import 后直接调用 ocr_prescription()
  2. 命令行：python prescription_ocr.py <图片路径> [--json]
"""

import os
import json
import sys

# ─── 单例引擎（首次调用时初始化，后续复用） ───
_engine = None
_engine_error = None


def _get_engine():
    """懒加载 OCR 引擎，全局只初始化一次"""
    global _engine, _engine_error
    if _engine is not None:
        return _engine
    if _engine_error is not None:
        raise ImportError(_engine_error)
    try:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
        return _engine
    except ImportError:
        _engine_error = (
            "RapidOCR未安装。请执行：pip install rapidocr-onnxruntime -i https://mirrors.aliyun.com/pypi/simple/"
        )
        raise ImportError(_engine_error)


def ocr_prescription(image_path):
    """
    识别处方图片中的文字。

    参数:
        image_path (str): 图片文件路径

    返回 (dict):
        {
            "success": True,
            "text": "完整文字（换行分隔）",
            "lines": ["行1", "行2", ...],
            "low_confidence": [{"text": "...", "confidence": 0.85}, ...],
            "engine": "RapidOCR"
        }
        或
        {
            "success": False,
            "error": "错误描述"
        }
    """
    if not os.path.exists(image_path):
        return {"success": False, "error": f"文件不存在: {image_path}"}

    try:
        ocr = _get_engine()
    except ImportError as e:
        return {"success": False, "error": str(e)}

    try:
        result, elapse = ocr(image_path)

        if not result:
            return {
                "success": True,
                "text": "",
                "lines": [],
                "low_confidence": [],
                "warning": "未检测到文字",
                "engine": "RapidOCR",
            }

        lines = []
        low_conf = []
        for box, text, confidence in result:
            lines.append(text)
            if confidence < 0.9:
                low_conf.append({"text": text, "confidence": round(confidence, 4)})

        return {
            "success": True,
            "text": "\n".join(lines),
            "lines": lines,
            "low_confidence": low_conf,
            "engine": "RapidOCR",
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── 命令行入口 ───

def main():
    if len(sys.argv) < 2:
        print("用法: python -X utf8 prescription_ocr.py <图片路径> [--json]")
        sys.exit(1)

    image_path = sys.argv[1]
    as_json = "--json" in sys.argv

    result = ocr_prescription(image_path)

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if not result["success"]:
            print(f"[错误] {result['error']}", file=sys.stderr)
            sys.exit(1)
        if not result.get("text"):
            print("[提示] 未检测到文字")
            sys.exit(0)
        print(result["text"])
        if result.get("low_confidence"):
            print("\n[低置信度，建议核对]")
            for item in result["low_confidence"]:
                print(f"  {item['text']} ({item['confidence']:.1%})")


if __name__ == "__main__":
    main()
