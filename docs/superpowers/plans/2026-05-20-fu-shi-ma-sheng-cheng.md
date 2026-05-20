# 复式码生成 5/6/7码切换 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将固定"七码复式"改为可切换5/6/7码的"复式码生成"，前后端均实现通用 N 码组合生成逻辑。

**Architecture:** 前端加码数下拉框联动输入，`generateCodeCombos(digits)` 泛化处理任意 N 码。后端新增同名函数及 `/api/generate_codes` 端点。前端可选调后端生成，也可本地生成填 textarea 预览。

**Tech Stack:** Python 3 (stdlib http.server), Vanilla JS, HTML/CSS

---

### Task 1: 后端 — 添加 `generate_code_combos` 函数

**Files:**
- Modify: `app.py` (在 `group_hit` 函数附近)
- Create: `tests/test_generate_code_combos.py`

- [ ] **Step 1: 写后端测试**

```python
import unittest
import app


class GenerateCodeCombosTest(unittest.TestCase):
    def test_5_code_generates_30_combos(self):
        result = app.generate_code_combos("01234")
        self.assertEqual(30, len(result))
        # 组六: C(5,3)=10, 组三: 5*4=20
        group6 = [n for n in result if len(set(n)) == 3]
        group3 = [n for n in result if len(set(n)) == 2]
        self.assertEqual(10, len(group6))
        self.assertEqual(20, len(group3))

    def test_6_code_generates_50_combos(self):
        result = app.generate_code_combos("012345")
        self.assertEqual(50, len(result))
        group6 = [n for n in result if len(set(n)) == 3]
        group3 = [n for n in result if len(set(n)) == 2]
        self.assertEqual(20, len(group6))
        self.assertEqual(30, len(group3))

    def test_7_code_generates_77_combos(self):
        result = app.generate_code_combos("0123456")
        self.assertEqual(77, len(result))
        group6 = [n for n in result if len(set(n)) == 3]
        group3 = [n for n in result if len(set(n)) == 2]
        self.assertEqual(35, len(group6))
        self.assertEqual(42, len(group3))

    def test_all_combos_use_only_input_digits(self):
        result = app.generate_code_combos("147")
        allowed = set("147")
        for n in result:
            self.assertTrue(set(n).issubset(allowed))

    def test_no_duplicates_in_result(self):
        result = app.generate_code_combos("01234")
        self.assertEqual(len(result), len(set(result)))

    def test_invalid_input_too_short_raises(self):
        with self.assertRaises(ValueError):
            app.generate_code_combos("01")

    def test_duplicate_digits_raises(self):
        with self.assertRaises(ValueError):
            app.generate_code_combos("01123")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_generate_code_combos.py -v`
Expected: FAIL — `AttributeError: module 'app' has no attribute 'generate_code_combos'`

- [ ] **Step 3: 在 `app.py` 中实现函数**

在 `group_hit` 函数之后插入：

```python
def generate_code_combos(digits):
    """Generate all 组六 + 组三 combos from N unique digits (N=3~8)."""
    digits = str(digits)
    if len(digits) < 3:
        raise ValueError("至少需要3个不同数字")
    if len(set(digits)) != len(digits) or not digits.isdigit():
        raise ValueError("数字必须是不重复的0-9数字")
    arr = list(digits)
    n = len(arr)
    result = []
    # 组六: C(n,3) — 三个不同数字
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                result.append(arr[i] + arr[j] + arr[k])
    # 组三: n * (n-1) — 一对 + 另一个数字
    for i in range(n):
        for j in range(n):
            if i != j:
                result.append(arr[i] + arr[i] + arr[j])
    return result
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_generate_code_combos.py -v`
Expected: 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_generate_code_combos.py
git commit -m "feat: add generate_code_combos backend function"
```

---

### Task 2: 后端 — 添加 `/api/generate_codes` 端点

**Files:**
- Modify: `app.py` (RequestHandler 类)
- Modify: `tests/test_generate_code_combos.py` (追加端点测试)

- [ ] **Step 1: 追加端点测试**

在 `tests/test_generate_code_combos.py` 末尾追加：

```python
import json
import io


class GenerateCodesEndpointTest(unittest.TestCase):
    def setUp(self):
        self.handler = app.RequestHandler(None, ("127.0.0.1", 5000), None)

    def _post_body(self, body_dict):
        payload = json.dumps(body_dict).encode("utf-8")
        return io.BytesIO(payload)

    def _call_generate(self, body_dict):
        self.handler.rfile = self._post_body(body_dict)
        self.handler.headers = {"Content-Length": "0"}
        self.handler.path = "/api/generate_codes"
        # Capture response
        self.handler.wfile = io.BytesIO()
        self.handler.do_POST()
        self.handler.wfile.seek(0)
        raw = self.handler.wfile.read()
        # Parse the HTTP response to get body
        body_start = raw.find(b"\r\n\r\n") + 4
        return json.loads(raw[body_start:])

    def test_endpoint_generates_5_code(self):
        resp = self._call_generate({"codes": [{"digits": "01234", "len": 5}]})
        self.assertTrue(resp.get("ok"))
        self.assertEqual(30, resp.get("count"))
        self.assertEqual(30, len(resp.get("generated", [])))

    def test_endpoint_generates_multiple_codes_merged(self):
        resp = self._call_generate({"codes": [
            {"digits": "01234", "len": 5},
            {"digits": "56789", "len": 5}
        ]})
        self.assertTrue(resp.get("ok"))
        self.assertEqual(60, resp.get("count"))

    def test_endpoint_empty_codes_returns_error(self):
        resp = self._call_generate({"codes": []})
        self.assertFalse(resp.get("ok"))
        self.assertIn("error", resp)
```

注意：由于 `RequestHandler` 构造函数需要 `(request, client_address, server)`，上述测试直接用 mock 可能有适配问题。如果构造困难，改为**手动调用函数**测试：

```python
class GenerateCodesEndpointLogicTest(unittest.TestCase):
    def test_generate_and_merge_5_code(self):
        from app import generate_code_combos
        result = generate_code_combos("01234")
        self.assertEqual(30, len(result))

    def test_generate_multiple_and_merge(self):
        from app import generate_code_combos
        merged = set()
        for digits in ["01234", "56789"]:
            merged.update(generate_code_combos(digits))
        self.assertEqual(60, len(merged))
```

实际端点通过启动服务器后 curl 手动验证。

- [ ] **Step 2: 运行测试确认基线通过**

Run: `python -m pytest tests/test_generate_code_combos.py -v`
Expected: 原有 7 tests + 新增 3 tests = 10 PASS（如果使用 function-test 版本）

- [ ] **Step 3: 在 `app.py` 中实现端点**

在 `do_POST` 的路径分派中加入：

```python
if self.path == "/api/generate_codes":
    return self._api_generate_codes()
```

然后添加方法：

```python
def _api_generate_codes(self):
    data = self._read_json_body()
    codes = data.get("codes", [])
    if not codes:
        self._send_json({"ok": False, "error": "请提供复式码列表"}, 400)
        return
    all_generated = set()
    for item in codes:
        digits = str(item.get("digits", ""))
        if not digits:
            continue
        try:
            combos = generate_code_combos(digits)
        except ValueError as e:
            self._send_json({"ok": False, "error": str(e)}, 400)
            return
        all_generated.update(combos)
    generated = sorted(all_generated)
    self._send_json({
        "ok": True,
        "generated": generated,
        "count": len(generated),
        "codes": [{"digits": c.get("digits", ""), "len": c.get("len", len(c.get("digits", "")))} for c in codes],
    })
```

- [ ] **Step 4: 启动服务器手动验证**

```bash
python app.py &
sleep 2
# 测试 5码
curl -s -X POST http://127.0.0.1:5000/api/generate_codes \
  -H "Content-Type: application/json" \
  -d '{"codes":[{"digits":"01234","len":5}]}' | python -c "import sys,json; d=json.load(sys.stdin); assert d['ok'] and d['count']==30, f'FAIL: {d}'; print('PASS 5码')"
# 测试 7码
curl -s -X POST http://127.0.0.1:5000/api/generate_codes \
  -H "Content-Type: application/json" \
  -d '{"codes":[{"digits":"0123456","len":7}]}' | python -c "import sys,json; d=json.load(sys.stdin); assert d['ok'] and d['count']==77, f'FAIL: {d}'; print('PASS 7码')"
# 测试混合
curl -s -X POST http://127.0.0.1:5000/api/generate_codes \
  -H "Content-Type: application/json" \
  -d '{"codes":[{"digits":"01234","len":5},{"digits":"56789","len":5}]}' | python -c "import sys,json; d=json.load(sys.stdin); assert d['ok'] and d['count']==60, f'FAIL: {d}'; print('PASS 混合')"
```

Expected: 三次均为 PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_generate_code_combos.py
git commit -m "feat: add /api/generate_codes endpoint"
```

---

### Task 3: 前端 — HTML/CSS 结构调整

**Files:**
- Modify: `index.html` (HTML 结构 + 少量 CSS)

- [ ] **Step 1: 修改 card-head 副标题**

将 `号码池 & 七码复式` → `号码池 & 复式码生成`

- [ ] **Step 2: 修改标题 label**

将：
```html
<label>七码复式 <span style="font-weight:400;color:var(--text-muted);font-size:11px;">（可选）</span></label>
```
改为：
```html
<label>复式码生成 <span style="font-weight:400;color:var(--text-muted);font-size:11px;">（可选）</span></label>
```

- [ ] **Step 3: 在 qima-selector 中加入码数下拉框**

将：
```html
<div class="qima-selector">
  <input id="qimaInput" placeholder="输入7个数字，如 0123456" maxlength="10">
  <button class="btn-secondary" id="qimaAddBtn" style="flex-shrink:0;">添加</button>
</div>
```
改为：
```html
<div class="qima-selector">
  <select id="qimaLenSelect" style="width:80px;flex-shrink:0;">
    <option value="5">5码</option>
    <option value="6">6码</option>
    <option value="7">7码</option>
  </select>
  <input id="qimaInput" placeholder="输入5个数字，如 01234" maxlength="5">
  <button class="btn-secondary" id="qimaAddBtn" style="flex-shrink:0;">添加</button>
</div>
```

- [ ] **Step 4: 修改提示文字**

将 helper：
```html
<span class="helper">输入7个不同数字，自动生成所有组六 + 组三组合。可添加多组七码，生成后合并去重填入上方号码池。</span>
```
改为：
```html
<span class="helper">选择码数并输入对应数量的不同数字，自动生成所有组六 + 组三组合。可添加多组不同码数，生成后合并去重填入上方号码池。</span>
```

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat: update input UI labels and add code-length dropdown"
```

---

### Task 4: 前端 — JS 逻辑改动

**Files:**
- Modify: `index.html` (JS 部分)

- [ ] **Step 1: 替换 `generateSevenCodeCombos` 为通用版本**

删除旧函数，在相同位置插入：

```javascript
function generateCodeCombos(digits) {
  var arr = digits.split(""), n = arr.length, result = [];
  // 组六: C(n,3)
  for (var i = 0; i < n; i++) for (var j = i+1; j < n; j++) for (var k = j+1; k < n; k++) result.push(arr[i] + arr[j] + arr[k]);
  // 组三: n * (n-1)
  for (var i = 0; i < n; i++) for (var j = 0; j < n; j++) if (i !== j) result.push(arr[i] + arr[i] + arr[j]);
  return result;
}
```

- [ ] **Step 2: 添加 `currentQimaLen` 状态和下拉框事件**

在变量声明区（`var qimaCodes = [];` 之后）添加：

```javascript
var currentQimaLen = 5;
```

在 `$("qimaAddBtn")` 事件绑定区添加：

```javascript
$("qimaLenSelect").addEventListener("change", function() {
  currentQimaLen = Number(this.value);
  $("qimaInput").placeholder = "输入" + currentQimaLen + "个数字，如 " + "0123456789".slice(0, currentQimaLen);
  $("qimaInput").maxLength = currentQimaLen;
});
```

- [ ] **Step 3: 改写 `addQima`**

```javascript
function addQima() {
  var raw = $("qimaInput").value.replace(/\s/g, "");
  var digits = [].filter.call(raw, function(v,i,a) { return a.indexOf(v) === i; }).join("");
  if (digits.length < currentQimaLen) return toast(currentQimaLen + "码至少需要" + currentQimaLen + "个不同数字");
  var exists = qimaCodes.some(function(item) { return item.digits === digits; });
  if (exists) return toast("该复式码已添加");
  qimaCodes.push({digits: digits, len: currentQimaLen});
  $("qimaInput").value = "";
  renderQimaList();
}
```

- [ ] **Step 4: 改写 `renderQimaList`**

```javascript
function renderQimaList() {
  $("qimaList").innerHTML = qimaCodes.map(function(item, i) {
    return '<span class="qima-tag">' + item.digits + ' <span style="font-size:10px;opacity:0.7">[' + item.len + '码]</span> <button data-action="remove-qima" data-idx="' + i + '">×</button></span>';
  }).join("");
  document.querySelectorAll("[data-action='remove-qima']").forEach(function(btn) {
    btn.addEventListener("click", function() { removeQima(Number(btn.dataset.idx)); });
  });
}
```

- [ ] **Step 5: 改写 `generateFromQima`**

```javascript
function generateFromQima() {
  if (!qimaCodes.length) return toast("请先添加复式码");
  var all = new Set();
  qimaCodes.forEach(function(item) {
    generateCodeCombos(item.digits).forEach(function(n) { all.add(n); });
  });
  var merged = Array.from(all).sort(), existing = $("inputArea").value.trim();
  $("inputArea").value = existing ? existing + "\n" + merged.join(" ") : merged.join(" ");
  toast("已生成 " + merged.length + " 组号码（" + qimaCodes.length + " 组复式码合并去重）");
}
```

- [ ] **Step 6: 改写 `clearAll` 重置 qimaCodes 和下拉框**

在 `clearAll` 函数中，将 `qimaCodes = [];` 后面追加：

```javascript
currentQimaLen = 5; $("qimaLenSelect").value = "5"; $("qimaInput").placeholder = "输入5个数字，如 01234"; $("qimaInput").maxLength = 5;
```

- [ ] **Step 7: Commit**

```bash
git add index.html
git commit -m "feat: generalize frontend code generation for 5/6/7 code"
```

---

### Task 5: 前端 — 演示数据更新

**Files:**
- Modify: `index.html` (loadDemo 函数)

- [ ] **Step 1: 更新 `loadDemo`**

在 `loadDemo` 中加上 qimaCodes 演示数据：

```javascript
function loadDemo() {
  $("inputArea").value = demoRaw; $("filterDigits").value = "357"; $("advanceDigits").value = ""; $("killDigits").value = "4";
  renderSegmentGroups([{mode:"2-3-5", groups:SEGMENT_DEMOS["2-3-5"]}, {mode:"5-5", groups:SEGMENT_DEMOS["5-5"]}]);
  renderCodeCardsFromFilters([{code_len:5, condition:"012", digits:"01234"}]);
  qimaCodes = [{digits: "01234", len: 5}, {digits: "123456", len: 6}];
  renderQimaList();
  currentQimaLen = 5; $("qimaLenSelect").value = "5";
  $("qimaInput").placeholder = "输入5个数字，如 01234"; $("qimaInput").maxLength = 5;
  toast("示例数据已填入，复式码5码+6码、段组和N码条件已添加");
}
```

- [ ] **Step 2: Commit**

```bash
git add index.html
git commit -m "feat: update demo data with 5-code and 6-code examples"
```

---

### Task 6: 文档更新

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新 README 中七码复式章节**

将 `七码复式` 段落改为：

```markdown
### 复式码生成

选择码数（5/6/7码）并输入对应数量的不同数字，自动生成所有组六 + 组三组合。可添加多组不同码数，合并去重后填入号码池。

| 码数 | 组六 | 组三 | 总注数 |
|------|------|------|--------|
| 5码  | C(5,3)=10 | 5×4=20 | 30 |
| 6码  | C(6,3)=20 | 6×5=30 | 50 |
| 7码  | C(7,3)=35 | 7×6=42 | 77 |
```

- [ ] **Step 2: 在 README 接口说明中加入新端点**

在 `POST /api/filter` 之后添加：

```markdown
### POST `/api/generate_codes`

```json
{
  "codes": [
    {"digits": "01234", "len": 5},
    {"digits": "56789", "len": 5}
  ]
}
```

返回：

```json
{
  "ok": true,
  "generated": ["001", "002", "..."],
  "count": 60,
  "codes": [{"digits": "01234", "len": 5}, {"digits": "56789", "len": 5}]
}
```
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update README for multi-code generation feature"
```

---

### Task 7: 端到端验证

- [ ] **Step 1: 运行全部后端测试**

Run: `python -m pytest tests/ -v`
Expected: 所有测试 PASS

- [ ] **Step 2: 启动服务器并手动验证前端**

```bash
python app.py
```

浏览器打开 `http://127.0.0.1:5000`，验证：
1. 下拉框默认显示"5码"，输入框 placeholder 为"输入5个数字，如 01234"
2. 切换到 6码/7码，输入框联动变化
3. 添加 5码 "01234"，标签显示 `01234 [5码]`
4. 添加 6码 "123456"，标签显示 `123456 [6码]`
5. 点击"生成并填入号码池"，textarea 填入组合
6. 点击"示例数据"，复式码区显示 5码+6码 示例
7. 点击"清空"，复式码区重置
8. 按"开始筛选"，正常筛选

- [ ] **Step 3: 验证后端 API**

```bash
curl -s -X POST http://127.0.0.1:5000/api/generate_codes \
  -H "Content-Type: application/json" \
  -d '{"codes":[{"digits":"01234","len":5}]}' | python -m json.tool
```
Expected: 返回 30 组号码

- [ ] **Step 4: Final commit (if any fixes)**

```bash
git add -A
git commit -m "chore: final verification adjustments"
```
