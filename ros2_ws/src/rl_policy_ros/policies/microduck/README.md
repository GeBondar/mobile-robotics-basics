# Политики Microduck

Девять ONNX-политик робота Microduck (Pollen Robotics) и их манифест — без изменений, как
опубликованы авторами.

| | |
|---|---|
| Источник | https://huggingface.co/pollen-robotics/microduck-policies |
| Ревизия | `665ae4eb20bfe13bca1ef4ea6d4bb6b4a096e448` |
| Лицензия | Apache-2.0 (указана в карточке модели) |
| Контракт | вход `obs [1, 61]`, выход `actions [1, 14]`, 50 Гц, нормализация вшита в граф |

Скачать ту же ревизию заново:

```bash
BASE=https://huggingface.co/pollen-robotics/microduck-policies/resolve/665ae4eb20bfe13bca1ef4ea6d4bb6b4a096e448
for n in alpha_walking alpha_stand alpha_sitstand alpha_ground_pick roulade ball_kick_left ball_kick_right roller roller_crouch; do curl -sL -o $n.onnx $BASE/$n.onnx; done
```

Восемь файлов побитово совпадают с теми, что скачивает
[приложение Б](<../../../../../appendix B (microduck policy inference)/README.md>).
`alpha_sitstand.onnx` и `manifest.json` в этой ревизии новее.

Сама модель робота (MJCF и меши, 23 МБ) в репозиторий не входит: `sim_node` берёт её из клона
`microduck_rl` по переменной окружения `MICRODUCK_RL`.

| Файл | Поведение | Как включается в `policy_node` |
|---|---|---|
| `alpha_walking.onnx` | ходьба по `/cmd_vel` | `auto`, когда команда ненулевая |
| `alpha_stand.onnx` | стойка | `auto`, когда команда нулевая |
| `ball_kick_left.onnx`, `ball_kick_right.onnx` | удар по мячу, 0.5 с | `/set_policy kick_left` |
| `roulade.onnx` | кувырок, 1.0 с | `/set_policy roulade` |
| `alpha_ground_pick.onnx` | наклон к полу | фазовая команда — в `policy_node` пока не поддержана |
| `alpha_sitstand.onnx` | сесть и встать | флаг позы — в `policy_node` пока не поддержан |
| `roller.onnx`, `roller_crouch.onnx` | роликовые коньки | нужна сцена `scene_rollers.xml` — пока не поддержана |
