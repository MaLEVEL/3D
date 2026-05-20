# 复式码生成：支持5/6/7码切换

## 目标

将"七码复式"改为可切换码数（5/6/7）的"复式码生成"，每次添加时选择码数，不同码数可混合使用。

## 不改动

- 后端 `app.py`：不涉及
- 筛选、段组、N码条件等其他功能：不动

## 改动清单（仅 `index.html`）

### 1. HTML 结构调整

**区域标题和副标题：**
- `七码复式` → `复式码生成`
- 副标题 `（可选）` 保留
- card-head-sub `号码池 & 七码复式` → `号码池 & 复式码生成`

**新增码数下拉框：**
- 在输入框左侧加 `<select>`，选项 `5码/6码/7码`，默认5码
- 输入框 placeholder 和 maxlength 随码数动态变化
- 布局：`[下拉框] [输入框] [添加按钮]`

### 2. JS 逻辑改动

**状态：**
- 新增 `currentQimaLen` 变量，记录当前选中的码数（默认5）
- `qimaCodes` 每项从纯字符串 `"0123456"` 改为 `{digits: "01234", len: 5}` 结构

**函数改动：**

| 改动 | 说明 |
|------|------|
| `addQima()` | 校验改为所选码数长度；存储 `{digits, len}` |
| `renderQimaList()` | 标签显示 `01234 [5码]` |
| `removeQima(idx)` | 无需改动 |
| `generateSevenCodeCombos(digits)` | 删除，替换为 `generateCodeCombos(digits)` |
| `generateCodeCombos(digits)` | 对 digits 长度 N 通用生成：组六 C(N,3) + 组三 N×(N-1) |
| `generateFromQima()` | 遍历 qimaCodes，对每项调用 `generateCodeCombos` |
| 码数下拉 change 事件 | 更新 `currentQimaLen`，更新输入框 placeholder/maxlength |
| `clearAll()` | 重置 `currentQimaLen` 为默认5码 |

**`generateCodeCombos(digits)` 实现：**
```
arr = digits 拆分为数组
result = []
// 组六：C(N,3) 三位不同数字
for i in 0..N-1:
  for j in i+1..N-1:
    for k in j+1..N-1:
      result.push(arr[i] + arr[j] + arr[k])
// 组三：对子 N×(N-1)
for i in 0..N-1:
  for j in 0..N-1:
    if i != j:
      result.push(arr[i] + arr[i] + arr[j])
return result
```

### 3. 演示数据更新

`loadDemo()` 中的 qimaCodes 示例改为包含不同码数：
- `[{digits: "01234", len: 5}, {digits: "123456", len: 6}]`

### 4. CSS

无需新增样式，复用现有 `.qima-selector` 布局，下拉框使用已有 `select` 样式。

## 数学验证

| 码数 | 组六 | 组三 | 总注数 |
|------|------|------|--------|
| 5码  | 10   | 20   | 30     |
| 6码  | 20   | 30   | 50     |
| 7码  | 35   | 42   | 77     |

## 边界情况

- 输入数字不足所选码数：toast 提示"X码至少需要X个不同数字"
- 重复添加同一组数字：按现有逻辑已处理（`qimaCodes.indexOf` → 需适配为新结构 `qimaCodes.find`)
- 未输入数字点击生成：toast 提示"请先添加复式码"

## 兼容性

- 历史记录不涉及 qimaCodes 存储，无迁移问题
- 已有 localStorage 数据不影响
- API 无变更
