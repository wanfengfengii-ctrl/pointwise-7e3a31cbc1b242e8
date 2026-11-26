# 社区触读卡工坊

展陈组提供预录的凸点单元和实际纸规。编排员修订触读稿，校对员检查每个单元在纸上的点位。领班冻结校样并登记交件目标，压台员按版在指定的实装纸上压纹。次班领班凭制卡首执和版次账点收成品。

## 运行

使用 Python 3.11 标准库。从项目根目录运行完整回归和环回示例。

```sh
python3 -B check_project.py
python3 -B -m tests.demo
python3 -B -m tests.trial_demo
```

`check_project.py` 运行完整回归；`tests.demo` 是普通制卡演练，`tests.trial_demo` 是试压续办与放行演练（含压前、压后失答及别纸竞争），`tests.trial_fixture` 是既有制卡对照，无新增请求。`python3 -B run_demo.py` 依次跑回归与这三个演练，任一失败即非零退出；运行清单的 `verify`/`demo` 分别指向 `check_project.py` 与 `run_demo.py`。

回归入口由控制台随项目提供。示例在自己的临时目录内使用两份 SQLite 文件和一个环回端口，完成后释放它们。单独启动持久服务时可以指定项目内的数据文件。

```sh
python3 -B -m record.operator_http --business workshop.sqlite --device press.sqlite --port 8000
```

服务只绑定 `127.0.0.1`。默认种子见 `samples/workshop.json`。首次启动登记 U、V、稿 `hall` 的修订 1、纸 A/B/C 及初始实装纸 B。用原文件重开时保留稿头、历史、校样、冻结版、目标、首执及设备状态。业务账和压台必须使用不同文件。

## 作业接口

请求和响应使用 UTF-8 JSON。POST 请求体为对象，最大 1 MiB。稿号、请求号和纸号是非空字符串且不含 NUL。路径中的稿号和请求号用 URL 编码。修订、校样号、版号和目标数用正整数表示。成功及同参复领均返回 200。

| 请求 | 请求体或路径参数 | 结果 |
| --- | --- | --- |
| `POST /manuscripts/hall/edit` | `{"expected_revision":1,"cells":["U","V"],"paper":{"width":9,"left":1,"right":2,"direction":"reverse"}}` | `manuscript_id`、新 `revision`、`cells` 和 `paper` |
| `POST /previews` | `{"manuscript_id":"hall","revision":2}` | `proof_id`、稿修订、纸规、排序后的 `points`、逐出现 `occurrences` |
| `POST /editions` | `{"proof_id":1,"target":2}`，可加 `"sample_paper_id":"A"` 指定试样 | `edition_id`、原校样和稿修订、冻结 `paper` 和 `points`，格式与原响应一致 |
| `GET /editions/1` | 版号 | 与冻结时相同的版次快照 |
| `POST /impressions` | `{"request_id":"make-B","edition_id":1,"paper_id":"B"}` | 含请求号、版号、实际纸号、`press_no`、稿修订和校样号的首执 |
| `GET /receipts/make-B` | 请求号 | 原确认首执 |
| `POST /proofs` | `{"request_id":"trial-A","edition_id":1,"paper_id":"A"}` | 试压实压首执；待核时 202 含 `request_id` 与 `"status":"pending"` |
| `GET /proofs/trial-A` | 试压请求号 | 原试压首执；待核时 202；未知 404 |
| `POST /editions/1/release` | `{"request_id":"trial-A"}` | `edition_id` 与核对过的试压首执 |
| `GET /editions/1/report` | 版号 | `target`、`completed`、`shortfall` 与按压次排列的 `pieces` |

编辑提交的预期修订过期时返回 `409 stale_revision`，含 `current_revision`。缺项、未知稿号和非法规格返回 422。预览可使用任一已保存修订，未知修订返回 404。越界返回 `422 outside_printable_area` 和 `violations`，每项包含 `cell_id`、`occurrence`、`point`，此次请求无校样号。未知校样或版号返回 404，非法目标返回 422。制卡的纸号与实装纸不符返回 `409 wrong_sheet`，已确认请求号改版或改纸返回 `409 request_conflict`。设备明确拒绝返回 `503 device_refusal`，回包丢失返回 `503 device_no_reply`。只有设备成功回包才登记普通制卡首执。压前与压后失答的原号查询都返回 404，压后原纸可能已有凸点。无确认首执的失答请求重投可能叠压。

试样相关错误：未知纸 404 `unknown_paper`，已压或已被指定的试样纸 409 `paper_conflict`，证据暂不可读时发行与试压均返回 202；普通版试压、纸号与指定试样不符 409 `trial_not_allowed`；试压原号改版或改纸、同版另号 409 `request_conflict`；试压版未放行制卡 409 `edition_not_released`，指定试样纸作正式件 409 `sample_paper_reserved`；未知试压原号 404 `unknown_trial`，普通版或他版试压号放行 409 `release_conflict`。试压与放行的细则见 TRIAL.md。

## 一天的样例

1. 编排员用 U、V 提交宽 6、左右边距各 1 的正向稿。
2. 校对员发现 V 第二次出现位置上的点 `(5,0)` 位于右边距，拿到含出处的越界报告。
3. 编排员将纸规改为宽 9、左边距 1、右边距 2，采用反向进纸。校对员得到合格校样。
4. 领班冻结该校样，登记目标两张。编排员随后另改稿件，领班仍可按已发版号读回原点阵。
5. 压台员在实装纸 B 上制作第一张，领回实压首执。交接账显示还欠一张。
6. 压台员换装 A 后完成第二张，领回另一实压压次。
7. 次班重开服务，按原号读回 B 的首执。即使 A 仍装在压台，同参重投亦只返回 B 的原首执。
8. 接班领班查版次账，确认 B、A 依实压次序列出，欠量为零，每件均可追至原稿修订和校样。

单元局部列为 0、1，局部行为 0、1、2，横向节距为 3。纸列从 0 起。对于第 i 个单元，i 从 0 起，阅读偏移为 `t = 3*i + dx`。正向纸面列为 `L + t`，反向为 `W - 1 - R - t`，纵坐标为 `dy`。纸面列须满足 `L <= x < W - R`。纸规使用整数格点，宽为正且边距非负并留有可压列。每次出现分别保留出处和局部点顺序，实际点阵按 `(x,y)` 排序。U 的局部点是 `(0,0)`、`(1,2)`，V 的局部点是 `(0,1)`、`(1,0)`。样例反向落点为 U 的 `(6,0)`、`(5,2)` 和 V 的 `(3,1)`、`(2,0)`。

## 本机压台夹具

压台侧只记录物理纸号、点阵和压次。服务启动后，可在同一项目目录中通过夹具 Python 接口操纵已初始化的设备文件。

```python
from press.mechanics import MechanicalPress

press = MechanicalPress('press.sqlite')
press.load('A')
print(press.inspect_loaded())
print(press.observe_paper('A'))
print(press.press_count())
```

`observe_paper` 返回纸面的凸点并集及该纸的实际压纹记录。`arm_refusal()` 明确拒绝下一次通过装纸检查的压纹。`arm_reply_loss('before')` 和 `arm_reply_loss('after')` 分别在实际动作前后丢回包，设备调用退出后不会迟发动作。`claim(owner, expected_paper)` 固定装纸并排除其他持有者压纹，`release(owner)` 解除独占。独占持久保存，装纸固定期间不可换纸。`schedule_load(paper_id)` 安排一次设备收命令时的实物换纸，可核验服务预检与设备动作之间的装纸变化。`set_evidence_available(False)` 暂停纸面和总数读回，设回 `True` 恢复。环回示例和测试通过同一套设备接口及 HTTP 入口作业。
