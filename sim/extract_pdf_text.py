#!/usr/bin/env python3
"""
extract_pdf_text.py - 提取 TOMAS-AGI 修正版 PDF 的关键文本内容
重点：数学公式、参数定义、算法描述、与代码实现相关的内容
"""
import sys
import os

# 尝试导入 pypdf 和 pdfplumber
try:
    from pypdf import PdfReader
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False
    print("[WARN] pypdf not available")

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    print("[WARN] pdfplumber not available")

PDFS = [
    "C:/Users/1/Downloads/太乙互搏 AGI——基于互搏架构的非结合通用人工智能理论（v2.0）——基于非结合谱图代数（NASGA）与谱投影折叠的通用智能范式(修正版).pdf",
    "C:/Users/1/Downloads/非结合谱图代数（NASGA）：TOMAS的统一数学框架及其低能唯象学（修正版）.pdf",
    "C:/Users/1/Downloads/基于非结合谱图代数（NASGA）重写太一互搏范式（TOMAS）论证万有理论的不可能性及基于信息存在度的互斥理论稳态替代方案(修正版).pdf",
    "C:/Users/1/Downloads/折叠深度  与普朗克常数  的对偶关系——基于 TOMAS 非结合谱代数框架的严格论证与物理检验(修正版).pdf",
]

def extract_with_pypdf(pdf_path, max_pages=20):
    """使用 pypdf 提取文本"""
    try:
        reader = PdfReader(pdf_path)
        text = ""
        num_pages = min(len(reader.pages), max_pages)
        for i in range(num_pages):
            page_text = reader.pages[i].extract_text()
            if page_text:
                text += f"\n=== 第 {i+1} 页 ===\n{page_text}\n"
        return text
    except Exception as e:
        return f"[ERROR] pypdf 提取失败: {e}"

def extract_with_pdfplumber(pdf_path, max_pages=20):
    """使用 pdfplumber 提取文本（保留布局）"""
    try:
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            num_pages = min(len(pdf.pages), max_pages)
            for i in range(num_pages):
                page_text = pdf.pages[i].extract_text()
                if page_text:
                    text += f"\n=== 第 {i+1} 页 (pdfplumber) ===\n{page_text}\n"
        return text
    except Exception as e:
        return f"[ERROR] pdfplumber 提取失败: {e}"

def extract_all_pdfs(max_pages=30):
    """提取所有 PDF 的前 N 页文本"""
    results = {}
    for pdf_path in PDFS:
        pdf_name = os.path.basename(pdf_path)
        print(f"\n{'='*60}")
        print(f"处理: {pdf_name}")
        print(f"{'='*60}")
        
        if not os.path.exists(pdf_path):
            print(f"[ERROR] 文件不存在: {pdf_path}")
            results[pdf_name] = "[ERROR] 文件不存在"
            continue
        
        text = ""
        if HAS_PDFPLUMBER:
            text = extract_with_pdfplumber(pdf_path, max_pages)
        elif HAS_PYPDF:
            text = extract_with_pypdf(pdf_path, max_pages)
        else:
            text = "[ERROR] 没有可用的 PDF 提取工具"
        
        results[pdf_name] = text
        # 打印前 2000 字符预览
        preview = text[:2000].replace("\n", " ")
        print(f"预览: {preview}...")
    
    return results

def search_keywords_in_text(text, keywords):
    """在文本中搜索关键词，返回匹配行"""
    lines = text.split("\n")
    matches = {}
    for kw in keywords:
        matches[kw] = []
        for i, line in enumerate(lines):
            if kw in line:
                # 返回匹配行前后各 1 行
                context = []
                if i > 0:
                    context.append(lines[i-1])
                context.append(line)
                if i < len(lines) - 1:
                    context.append(lines[i+1])
                matches[kw].append("\n".join(context))
    return matches

def analyze_pdf_content(pdf_path, max_pages=50):
    """分析 PDF 内容，提取关键信息"""
    if HAS_PDFPLUMBER:
        extractor = extract_with_pdfplumber
    elif HAS_PYPDF:
        extractor = extract_with_pypdf
    else:
        return {"error": "No PDF extractor available"}
    
    text = extractor(pdf_path, max_pages)
    
    # 搜索与代码实现相关的关键词
    keywords = [
        "八元数", "Octonion", "Fano", "范诺",
        "结合子", "associator", "非结合",
        "xi_c", "ξ_c", "效能指标",
        "NASGA", "谱图", "Laplacian",
        "kappa", "κ", "稳定",
        "A6-BS", "基准", "benchmark",
        "折叠深度", "fold", "投影",
        "信息存在度", "I(X)",
        "修正", "修改", "更新", "change", "update",
    ]
    
    matches = search_keywords_in_text(text, keywords)
    
    return {
        "text_preview": text[:5000],
        "keywords_found": {k: len(v) for k, v in matches.items() if len(v) > 0},
        "matches": {k: v[:3] for k, v in matches.items() if len(v) > 0},
    }

if __name__ == "__main__":
    print("TOMAS-AGI 修正版 PDF 内容提取工具")
    print("=" * 60)
    
    if not HAS_PYPDF and not HAS_PDFPLUMBER:
        print("[ERROR] 请先安装 pypdf 或 pdfplumber")
        sys.exit(1)
    
    # 提取所有 PDF 内容
    results = extract_all_pdfs(max_pages=30)
    
    # 保存结果到文件
    output_dir = "C:/Users/1/WorkBuddy/2026-06-13-01-47-22/tomas_agi/docs"
    os.makedirs(output_dir, exist_ok=True)
    
    for pdf_name, text in results.items():
        safe_name = pdf_name.replace(" ", "_").replace("（", "_").replace("）", "_")[:100]
        output_path = os.path.join(output_dir, f"{safe_name}_extract.txt")
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"[OK] 已保存: {output_path}")
        except Exception as e:
            print(f"[ERROR] 保存失败 {output_path}: {e}")
    
    print("\n提取完成！")
