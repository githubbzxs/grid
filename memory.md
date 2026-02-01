# 馃 Project Memory (椤圭洰璁板繂搴?

> 娉ㄦ剰锛氭鏂囦欢鐢?Agent 鑷姩缁存姢銆傛瘡娆′細璇濈粨鏉熸垨閲嶈鍙樻洿鍚庡繀椤绘洿鏂般€?> 鐩殑锛氫綔涓洪」鐩殑闀挎湡璁板繂锛岀‘淇濅笂涓嬫枃鍦ㄤ笉鍚屼細璇濆拰 Sub-Agents 涔嬮棿鏃犳崯浼犻€掋€?
## 1. 馃搷 Current Status (褰撳墠鐘舵€?

**褰撳墠闃舵**: [ 馃摑 瑙勫垝涓?]
**褰撳墠浠诲姟**:
- [ ] 杩滅▼鏈嶅姟鍣ㄩ噸鏂伴儴缃诧紙鎸囧畾鏈嶅姟鍣?45.207.211.121:22 root锛屽緟纭閮ㄧ讲鏂瑰紡/椤圭洰璺緞/鏈嶅姟绠＄悊鏂瑰紡/鐩爣鐗堟湰锛?
**涓嬩竴姝ヨ鍒?*:
- [ ] 鑾峰彇杩滅▼椤圭洰璺緞涓庨儴缃叉柟寮忥紙鑴氭湰/瀹瑰櫒/鎵嬪姩锛?- [ ] 纭鏈嶅姟绠＄悊鏂瑰紡锛坰ystemd/docker/pm2 绛夛級
- [ ] 鏄庣‘鐩爣鐗堟湰锛堥粯璁?main 鎴栨寚瀹氬垎鏀?tag/commit锛?
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
- 榛樿绔彛: 9999锛堢洃鍚?127.0.0.1锛?- 鐜鍙橀噺: `GRID_HOST`銆乣GRID_PORT`銆乣GRID_DATA_DIR`
- 杩愯鍙傛暟: `runtime.simulate_fill`锛堟ā鎷熸ā寮忓紑鍏筹級

## 3. 馃彈 Architecture & Patterns (鏋舵瀯涓庢ā寮?

**鐩綍缁撴瀯瑙勮寖**:
- `apps/server/app`: FastAPI 涓绘湇鍔′笌涓氬姟閫昏緫
- `apps/server/app/web`: 闈欐€?WebUI
- `apps/server/app/exchanges`: 浜ゆ槗鎵€閫傞厤锛圠ighter / Paradex / GRVT锛?- `apps/server/app/strategies`: 绛栫暐瀹炵幇
- `scripts`: 閮ㄧ讲涓庣淮鎶よ剼鏈?
**鏍稿績璁捐妯″紡**:
- 浣跨敤 `app/core/config_store` 缁熶竴璇诲啓閰嶇疆
- 浜ゆ槗鎵€閫傞厤鍣ㄥ垎灞傜粍缁?- AS 绛栫暐閫氳繃杩愯鏃堕厤缃枃浠惰瀵熷苟椹卞姩鏇存柊閫昏緫

## 4. 馃摑 Key Decisions Log (鍏抽敭鍐崇瓥璁板綍)

- **[2026-02-01]**: 鍥哄畾浣跨敤杩滅▼鏈嶅姟鍣?45.207.211.121:22锛坮oot锛夎繘琛岄噸鏂伴儴缃层€?- **[2026-02-01]**: GRVT 鎺ュ叆浣跨敤 SDK锛學S 涓嬪崟浣跨敤 SDK 鍐呮柟娉曘€?- **[2026-02-01]**: 璧勯噾鍒掕浆鏀逛负瀹屾暣鍒掕浆涓庝綑棰濇娴嬩紭鍏堛€?- **[2026-02-01]**: 淇 AS 绛栫暐妯″紡骞朵繚鐣?Avellaneda-Stoikov 閰嶇疆瑙傚療銆?- **[2026-02-01]**: Lighter 鐨?OrderApi.trades limit 鍥哄畾涓?100銆?- **[2026-02-01]**: WebUI 澧炲姞 AS 绛栫暐璇存槑鏂囨銆?
## 5. 鈿狅笍 Known Issues & Constraints (宸茬煡闂涓庣害鏉?

- 鏆傛棤宸茬煡闂銆?
## 6. 馃帹 User Preferences (鐢ㄦ埛鍋忓ソ)

- 鎵€鏈夎嚜鐒惰瑷€鍥炲浣跨敤涓枃銆?- 娉ㄩ噴涓庢枃妗ｅ繀椤讳娇鐢ㄤ腑鏂囷紝缁熶竴 UTF-8 缂栫爜銆?- 閬靛惊 KISS 涓?SOLID銆?- 鍙戠幇缂洪櫡浼樺厛淇鍐嶆墿灞曘€?- 绂佹 MVP 鎴栧崰浣嶅疄鐜般€?- 鏈夋敼鍔ㄩ渶鑷姩鎻愪氦骞舵帹閫佽繙绔粨搴撱€?
---

**Last Updated**: 2026-02-01 21:07

