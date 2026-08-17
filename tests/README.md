# tests · 自检

本目录用于技能自检，确保脚本可运行、模板占位符完整。

## 自检项

1. **脚本语法检查**：

   ```bash
   python -m py_compile scripts/make-queries.py
   python -m py_compile scripts/verify-links.py
   ```

2. **make-queries.py 运行检查**（生成检索清单）：

   ```bash
   python scripts/make-queries.py --person "示例人物" --company "示例公司" --role "采购总监"
   ```

3. **verify-links.py 校验检查**（对报告做链接校验）：

   ```bash
   python scripts/verify-links.py <报告.html> "目标人名"
   ```

4. **模板占位符完整性**：`report-template.html` 的所有 `{{占位符}}` 必须能在报告中全部填充，无残留。

## 通过标准

- 所有脚本语法通过、可运行
- 校验脚本对有效链接返回 OK，对无效链接返回 FAIL 并列出问题链接
- 模板占位符无残留
