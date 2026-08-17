#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify-links.py · 报告链接真实性校验（交付前必跑）

用法：
    python verify-links.py <报告.html> <目标实体名> [--strict]

校验三道关，任一不过即 FAIL（不允许交付）：
  1. 可打开：HTTP 状态 2xx/3xx
  2. 非空壳：页面内容长度 >= 500 字节
  3. 内容相关：页面文本包含目标实体名（公司名/人名）

FAIL 行为（模型必须执行，缺一不可）：
  - 不允许交付带无效链接的报告。
  - 必须重新检索，把无效链接/无来源内容替换为「有真实链接 + 有来源标注 + 有真实信息」的内容。
  - 找不到真实来源时，换写另一块有真实来源的内容，报告每一块都必须是实内容。
  - 全部通过校验后才允许交付；不允许卡住不交付。
"""
import sys
import re
import urllib.request
import urllib.error
import ssl
import time

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
MIN_BYTES = 500
TIMEOUT = 15
MAX_LINKS = 60

# 反爬站点：对爬虫常返回空页/验证页/极小内容，但浏览器可打开。
# 对这些站点只校验「HTTP 可打开（2xx/3xx）」，豁免「非空壳」和「内容含实体名」校验，避免误伤真实链接。
ANTI_BOT_DOMAINS = (
    "weibo.com", "weibo.cn", "douyin.com", "iesdouyin.com",
    "linkedin.com", "x.com", "twitter.com", "xiaohongshu.com",
    "zhihu.com", "zhipin.com", "liepin.com", "zhaopin.com",
    "51job.com", "58.com", "qixin.com", "qcc.com", "tianyancha.com",
    "aiqicha.baidu.com", "antgroup.com", "huawei.com",
    "toutiao.com", "baike.com", "baidu.com", "sohu.com",
    "163.com", "sina.com", "sina.cn", "qq.com", "ifeng.com",
    "people.com.cn", "cnr.cn", "eastmoney.com", "jiemian.com",
    "thepaper.cn", "caixin.com", "yicai.com", "36kr.com",
    "ithome.com", "zealer.com", "gov.cn",
)

# 低可信域名：第三方聚合站/来源不明的站点，可靠性低、常对浏览器拦截，
# 即使脚本能读到内容也直接判 FAIL，要求模型换主渠道来源（天眼查/企查查/爱企查/官网等）。
LOW_TRUST_DOMAINS = (
    "12580.tv", "tianyancha.com.cn", "qixin.com.cn", "gsxt.tv",
    "maigoo.com", "chanpin100.com",
)


def fetch(url: str):
    """返回 (status, body_bytes)。失败抛异常。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
        body = resp.read()
        return resp.status, body


def main():
    if len(sys.argv) < 3:
        print("[FAIL] 用法: python verify-links.py <报告.html> <目标实体名>")
        sys.exit(2)

    report_path = sys.argv[1]
    entity = sys.argv[2].strip()

    with open(report_path, "r", encoding="utf-8") as f:
        html = f.read()

    hrefs = re.findall(r'href="([^"]+)"', html)
    links = [h for h in hrefs if h.startswith("http")]
    links = list(dict.fromkeys(links))[:MAX_LINKS]

    print(f"报告: {report_path}")
    print(f"目标实体: {entity}")
    print(f"去重后链接数: {len(links)}")
    print("-" * 60)

    results = []
    for url in links:
        try:
            status, body = fetch(url)
            text = body.decode("utf-8", errors="ignore")
            content_len = len(text)
            host = url.split("/")[2].lower() if "//" in url else ""
            is_low_trust = any(d in host for d in LOW_TRUST_DOMAINS)
            if is_low_trust:
                # 低可信域名：直接 FAIL，要求模型换主渠道来源
                results.append((url, status, content_len, "低可信", False))
                print(f"[FAIL] {status} | {content_len}B | 低可信域名 | {url[:90]}")
                time.sleep(0.3)
                continue
            is_antibot = any(d in host for d in ANTI_BOT_DOMAINS)
            if is_antibot:
                # 反爬站：只校验 HTTP 可打开（2xx/3xx），豁免非空壳与内容校验（反爬站对爬虫返回极小内容，但浏览器可开）
                ok = (200 <= status < 400)
                results.append((url, status, content_len, "豁免", ok))
                mark = "OK " if ok else "FAIL"
                print(f"[{mark}] {status} | {content_len}B | 反爬豁免 | {url[:90]}")
            else:
                related = entity in text
                ok = (200 <= status < 400) and (content_len >= MIN_BYTES) and related
                results.append((url, status, content_len, related, ok))
                mark = "OK " if ok else "FAIL"
                print(f"[{mark}] {status} | {content_len}B | 含实体名:{related} | {url[:90]}")
        except Exception as e:
            results.append((url, "ERR", 0, False, False))
            print(f"[FAIL] ERR {type(e).__name__} | {url[:90]}")
        time.sleep(0.3)

    bad = [r for r in results if not r[4]]
    print("-" * 60)

    # ===== 内容校验（person-brief 专用） =====
    content_issues = []
    with open(report_path, "r", encoding="utf-8") as f:
        html = f.read()

    # 1. 占位符残留
    for banned in ["{{", "}}", "（示例", "TODO"]:
        if banned in html:
            content_issues.append(f"发现模板残留: {banned}")

    # 2. 表格来源列不能为空：内容点必须在「来源列(td.src)」有来源按钮
    #    表格行结构：<tr><td class="lb">标签</td><td>内容</td><td class="src">来源</td></tr>
    rows = re.findall(r"<tr><td class=\"lb\">([^<]*)</td><td>(.*?)</td><td class=\"src\">(.*?)</td></tr>", html, re.S)
    for label, content, src in rows:
        # 内容列里不应直接放 srclink（应放来源列）
        if "srclink" in content and "srclink" not in src:
            content_issues.append(f"来源按钮放错位置（应在来源列）: {label}")
        # 来源列应该非空（除非如实标注未检索到）
        if not src.strip() and "srclink" in content:
            content_issues.append(f"来源列为空但内容有链接: {label}")

    # 3. 社媒表操作列检查：第 3 列只放「进入主页」按钮或留空，禁止 srclink / 长文字
    #    社媒表行结构：<tr><td>平台</td><td>账号信息</td><td>操作</td></tr>（无 class="lb"）
    sm_rows_html = re.findall(r"<table class=\"sm\">.*?<tbody>(.*?)</tbody>", html, re.S)
    for sm_body in sm_rows_html:
        sm_trs = re.findall(r"<tr>(.*?)</tr>", sm_body, re.S)
        for tr in sm_trs:
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if len(tds) >= 3:
                op = tds[2]  # 第 3 列 = 操作列
                op_text = re.sub(r"<[^>]+>", "", op).strip()
                if "srclink" in op:
                    content_issues.append(f"社媒操作列出现 srclink（应只放进入主页按钮或留空）")
                if "未检索到" in op_text or "仅见报道提及" in op_text:
                    content_issues.append(f"社媒操作列出现「未检索到」（应写在第2列账号信息，操作列留空）: {op_text[:20]}")
                if len(op_text) > 8 and "进入主页" not in op:
                    content_issues.append(f"社媒操作列文字过长（应只放按钮或留空）: {op_text[:20]}")

    # 4. 敏感词检查：报告不允许出现敏感词（命中即 FAIL，列出上下文供模型修正）
    SENSITIVE_WORDS = (
        "据说", "可能", "唯一", "龙头", "第一品牌", "最佳", "最优秀", "遥遥领先",
        "全国第一", "世界第一", "全球领先", "顶级", "巨头", "霸主", "绝对", "必然",
        "号称", "自称", "谣传", "爆料", "知情人士", "内部消息", "小道消息",
        "保密", "机密", "绝密", "诈骗", "洗钱", "赌博", "行贿", "受贿", "贪污",
        "腐败", "回扣", "内幕", "黑幕", "违规", "违法", "犯罪", "自杀", "跳楼",
        "凶杀", "家暴", "霸凌", "歧视", "诽谤", "造谣", "传谣", "潜规则",
        "灰色地带", "洗白",
    )
    for w in SENSITIVE_WORDS:
        idx = html.find(w)
        if idx != -1:
            ctx = html[max(0, idx - 20): idx + len(w) + 20].replace("\n", " ")
            content_issues.append(f"敏感词「{w}」上下文: …{ctx}…")

    # 5. HTML 结构检查：容器标签开闭不平衡会导致排版变形（div 多/少闭合等）
    import html.parser as _hp
    _VOID = {"br", "img", "hr", "meta", "link", "input", "area", "base", "col",
             "embed", "source", "track", "wbr", "path", "circle", "rect", "line"}
    _CONTAINER = {"wrap", "sec", "foot", "head", "quick", "ice", "dual", "gap",
                  "avoid", "hook", "timeline", "appendix", "note", "risk", "col"}

    class _Struct(_hp.HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack = []
            self.stray = []
            self.close_marks = []
        def handle_starttag(self, tag, attrs):
            if tag not in _VOID:
                d = dict(attrs)
                self.stack.append((tag, d.get("class", ""), self.getpos()[0]))
        def handle_endtag(self, tag):
            if tag in _VOID:
                return
            ln, _ = self.getpos()
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    self.close_marks.append((ln, self.stack[i][1], self.stack[i][2]))
                    del self.stack[i]
                    return
            self.stray.append(f"L{ln}: 多余的闭合 </{tag}>（无配对开始标签）")

    for t in ("div", "table", "style", "section", "ul", "ol", "tr", "td", "th"):
        opens = len(re.findall(r"<%s[\s>]" % t, html))
        closes = len(re.findall(r"</%s>" % t, html))
        if opens != closes:
            diff = closes - opens
            mark = "多" if diff > 0 else "少"
            content_issues.append(
                f"<{t}> 开 {opens} / 闭 {closes} 不平衡（{mark} {abs(diff)} 个闭合标签）—— "
                f"会导致排版变形，模型必须逐段核对每个区块的开闭配对并修正"
            )
    _sp = _Struct()
    _sp.feed(html)
    for s in _sp.stray:
        content_issues.append(s)
    if _sp.stack:
        from collections import Counter as _Cnt
        left = _Cnt(t for t, _ in _sp.stack)
        top = ", ".join(f"{t}×{n}" for t, n in left.most_common(6))
        content_issues.append(f"存在未闭合标签: {top}（div/table/style 等必须开闭配对）")
    # 定位多写闭合：某行连续闭合多个 div，且其中闭合了「更早行打开」的区块容器（sec/wrap 等）
    from collections import defaultdict as _DD
    _by_line = _DD(list)
    for ln, cls, open_ln in _sp.close_marks:
        _by_line[ln].append((cls, open_ln))
    for ln in sorted(_by_line):
        items = _by_line[ln]
        if len(items) >= 2:
            hit = [c for c, o in items if ((c.split() or [""])[0]) in _CONTAINER and o < ln]
            if hit:
                content_issues.append(
                    f"提示 L{ln}: 该行连续闭合 {len(items)} 个 div，其中提前闭合了更早行打开的区块容器 {hit}——"
                    f"重点检查此处是否多写了一个闭合标签"
                )

    if content_issues:
        print(f"[FAIL] 内容校验 {len(content_issues)} 项不合格：")
        for c in content_issues:
            print(f"  - {c}")
        print("要求：模型必须修正上述内容后重新校验，全部通过才允许交付。")
        sys.exit(1)

    if bad:
        print(f"[FAIL] {len(bad)}/{len(results)} 个链接无效：")
        for url, status, clen, rel, _ in bad:
            print(f"  - {url}")
        print("要求：模型必须重新检索，将上述无效链接替换为真实可用链接，")
        print("      重新校验全部通过后才允许交付。")
        sys.exit(1)
    else:
        print(f"[OK] 全部 {len(results)} 个链接通过校验，允许交付。")
        sys.exit(0)


if __name__ == "__main__":
    main()
