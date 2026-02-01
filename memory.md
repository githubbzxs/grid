# 馃 Project Memory (椤圭洰璁板繂搴?

> 娉ㄦ剰锛氭鏂囦欢鐢?Agent 鑷姩缁存姢銆傛瘡娆′細璇濈粨鏉熸垨閲嶈鍙樻洿鍚庡繀椤绘洿鏂般€?> 鐩殑锛氫綔涓洪」鐩殑闀挎湡璁板繂锛岀‘淇濅笂涓嬫枃鍦ㄤ笉鍚屼細璇濆拰 Sub-Agents 涔嬮棿鏃犳崯浼犻€掋€?
## 1. 馃搷 Current Status (褰撳墠鐘舵€?

**褰撳墠闃舵**: [ 鉁?宸蹭氦浠?]
**褰撳墠浠诲姟**:
- [x] 鍔ㄦ€佺綉鏍间笌 AS 缃戞牸褰诲簳鍒嗗紑锛圵ebUI 鍒嗚〃閰嶇疆锛?- [x] AS 缃戞牸浠呮寕涓ゅ崟锛? bid + 1 ask锛?- [x] AS 缃戞牸椋庢帶鏀逛负鏈€澶у洖鎾や繚鎶わ紙as_max_drawdown锛?- [x] AS 鏂板浠峰樊涔樻暟鍙傛暟锛坅s_step_multiplier锛?- [x] 淇 Lighter 璐︽埛缁熻璇诲彇璐︽埛涓嶅尮閰嶉棶棰?
**涓嬩竴姝ヨ鍒?*:
- [ ] 濡傞渶涓婄嚎锛岄儴缃插埌 45.207.211.121 骞堕噸鍚?grid.service
- [ ] 濡傞渶鍋ュ悍妫€鏌ャ€佸煙鍚?SSL 鎴栫鍙ｈ皟鏁达紝缁х画澶勭悊

## 2. 馃洜 Tech Stack & Config (鎶€鏈爤涓庨厤缃?

| 绫诲埆 | 閫夊瀷/鐗堟湰 | 澶囨敞 |
| --- | --- | --- |
| **Language** | Python 3.11+ | FastAPI 鏈嶅姟绔?|
| **Framework** | FastAPI + Uvicorn | API + WebUI |
| **Crypto** | cryptography | 瀵嗛挜鍔犺В瀵?|
| **SDK** | lighter-python / paradex-py / grvt-pysdk | 浜ゆ槗鎵€ SDK |
| **Storage** | JSON 鏂囦欢 | `data/config.json`銆乣data/runtime_history.jsonl` |

**鍏抽敭鐜閰嶇疆**:
- Python Version: >= 3.11
- 榛樿绔彛: 9999锛堢洃鍚?0.0.0.0锛?- 鐜鍙橀噺: `GRID_HOST`銆乣GRID_PORT`銆乣GRID_DATA_DIR`
- 杩愯鍙傛暟: `runtime.simulate_fill`锛堟ā鎷熸ā寮忓紑鍏筹級

## 3. 馃彈 Architecture & Patterns (鏋舵瀯涓庢ā寮?

**鐩綍缁撴瀯瑙勮寖**:
- `apps/server/app`: FastAPI 涓绘湇鍔′笌涓氬姟閫昏緫
- `apps/server/app/web`: 闈欐€?WebUI
- `apps/server/app/exchanges`: 浜ゆ槗鎵€閫傞厤锛圠ighter / Paradex / GRVT锛?- `apps/server/app/strategies`: 绛栫暐瀹炵幇
- `scripts`: 閮ㄧ讲涓庣淮鎶よ剼鏈?
**閮ㄧ讲缁撴瀯**:
- 鏈嶅姟鍣ㄤ粨搴撹矾寰? `/root/grid`
- Python 铏氭嫙鐜: `/root/grid/.venv`
- systemd 鏈嶅姟: `/etc/systemd/system/grid.service`
- 鏈嶅姟鍚姩: `/root/grid/.venv/bin/python -m uvicorn app.main:app --app-dir apps/server --host 0.0.0.0 --port 9999`

**鏍稿績璁捐妯″紡**:
- 浣跨敤 `app/core/config_store` 缁熶竴璇诲啓閰嶇疆
- 浜ゆ槗鎵€閫傞厤鍣ㄥ垎灞傜粍缁?- 鍔ㄦ€佺綉鏍间笌 AS 缃戞牸鍦?UI 鍒嗚〃閰嶇疆锛屽悗绔€氳繃 `grid_mode` 鍖哄垎
- AS 鏈€灏忎环宸娇鐢?`as_min_step`锛岃嫢 <=0 鍒欏洖閫€鍒?`grid_step` 鎴栨渶灏忎环鏍煎埢搴?- AS 鎸傚崟鍥哄畾涓ゅ崟锛? bid + 1 ask锛?- AS 椋庢帶浣跨敤鏈€澶у洖鎾ら槇鍊?`as_max_drawdown`
- AS 浠峰樊涔樻暟浣跨敤 `as_step_multiplier`

## 4. 馃摑 Key Decisions Log (鍏抽敭鍐崇瓥璁板綍)

- **[2026-02-02]**: AS 鏂板浠峰樊涔樻暟 `as_step_multiplier`锛岀敤浜庣缉鏀?AS 浠峰樊銆?- **[2026-02-02]**: 淇 Lighter 缁熻璇诲彇閿欒璐︽埛瀵艰嚧鐨?0 缁熻闂銆?- **[2026-02-01]**: 鍔ㄦ€佺綉鏍间笌 AS 缃戞牸褰诲簳鍒嗗紑锛學ebUI 浣跨敤鐙珛琛ㄦ牸閰嶇疆銆?- **[2026-02-01]**: AS 缃戞牸浠呮寕涓ゅ崟锛屽彇娑堝浣欐寕鍗曞苟鍗曠嫭鎺у埗灞傜骇銆?- **[2026-02-01]**: AS 椋庢帶鏀逛负鏈€澶у洖鎾や繚鎶?`as_max_drawdown`锛岃Е鍙戝垯绱ф€ュ仠姝€?- **[2026-02-01]**: 鐢熶骇閮ㄧ讲鍥哄畾鍦?45.207.211.121:22锛坮oot锛夛紝浠撳簱璺緞 `/root/grid`锛屼娇鐢?systemd `grid.service`銆?
## 5. 鈿狅笍 Known Issues & Constraints (宸茬煡闂涓庣害鏉?

- 鏆傛棤宸茬煡闂銆?
## 6. 馃帹 User Preferences (鐢ㄦ埛鍋忓ソ)

- 鎵€鏈夎嚜鐒惰瑷€鍥炲浣跨敤涓枃銆?- 娉ㄩ噴涓庢枃妗ｅ繀椤讳娇鐢ㄤ腑鏂囷紝缁熶竴 UTF-8 缂栫爜銆?- 閬靛惊 KISS 涓?SOLID銆?- 鍙戠幇缂洪櫡浼樺厛淇鍐嶆墿灞曘€?- 绂佹 MVP 鎴栧崰浣嶅疄鐜般€?- 鏈夋敼鍔ㄩ渶鑷姩鎻愪氦骞舵帹閫佽繙绔粨搴撱€?
---

**Last Updated**: 2026-02-02 06:55

