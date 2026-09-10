# Урок 13: Microduck — симулятор MuJoCo с RL-политиками

**Цель:** получить работающий MuJoCo-симулятор робота Microduck, управляемый обученными
нейросетевыми политиками (ONNX), и научиться «тыкать» в него с клавиатуры.

**Что нужно:** Windows 10/11 + Python 3.12 (устанавливается через `uv`), около 3 ГБ диска.
GPU не обязателен — инференс и физика работают на CPU (обучение политик — это другой
репозиторий и отдельная история).

---

## 1. Что такое Microduck

[Microduck](https://github.com/pollen-robotics/microduck) — маленький двуногий робот
(~25 см, ~800 г, 14 сервомоторов Dynamixel XL330 + привод челюсти). Он **не запрограммирован
классически**: походкой управляют нейросетевые политики (PPO), обученные в MuJoCo и
экспортированные в ONNX. На самом роботе их выполняет демон `robotd` на частоте 50 Гц.

Два репозитория:

| Репозиторий | Что внутри |
|---|---|
| [`microduck`](https://github.com/pollen-robotics/microduck) | «Мозг» робота: демоны на Rust (`robotd`, `tofd`, `mediad`…), цикл управления 50 Гц, IPC, политики |
| [`microduck_rl`](https://github.com/pollen-robotics/microduck_rl) | Обучение политик (MuJoCo Warp + PPO) и **симулятор**: сцены, модель робота, `duck-body`, скрипт инференса |

В этом уроке мы запускаем инференс готовых политик в MuJoCo через скрипт
`scripts/infer_policy.py` из `microduck_rl`. Полный «настоящий» симулятор
(`robotd --sim` + `duck-body`, те самые демоны с робота) — следующий шаг, см. раздел 9.

## 2. Структура урока

```
appendix B (microduck policy inference)/
├── README.md                  ← этот файл
├── microduck/                 ← ваш форк (git clone, не трекается курсом)
├── microduck_rl/              ← оригинал репозитория с симулятором
├── policies/                  ← скачанные ONNX-политики (Hugging Face)
└── code/
    └── infer_policy_windows.py ← адаптация infer_policy.py под Windows (клавиатура)
```

## 3. Форк и клонирование

Форк уже создан: **`github.com/GeBondar/microduck`** (исходник — `pollen-robotics/microduck`).
Воспроизвести на любой машине:

```powershell
gh repo fork pollen-robotics/microduck --clone=false

git clone https://github.com/<YOU>/microduck.git microduck
git -C microduck remote add upstream https://github.com/pollen-robotics/microduck.git

# репозиторий с симулятором (форкать не обязательно — мы его не меняем)
git clone https://github.com/pollen-robotics/microduck_rl.git microduck_rl
```

## 4. Окружение Python (`uv`)

`microduck_rl` управляется через [uv](https://docs.astral.sh/uv/) и требует Python 3.12.

```powershell
uv --version          # нет? установите: irm https://astral.sh/uv/install.ps1 | iex

cd microduck_rl
uv sync               # ~5-10 мин: mujoco 3.10, onnxruntime, torch (CPU), bam, warp-lang
uv run python -c "import mujoco, onnxruntime; from bam.model import load_model; print('OK')"
```

Ожидаемый результат: `OK`, без ошибок импорта.

## 5. Политики с Hugging Face

Официальный набор политик лежит в `pollen-robotics/microduck-policies`
(формат ONNX, вход `obs[1,61]`, выход `actions[1,14]`, нормализация уже «вшита» в граф).

```powershell
cd ..   # appendix B (microduck policy inference)
mkdir policies
$base = "https://huggingface.co/pollen-robotics/microduck-policies/resolve/main"
foreach ($n in "alpha_walking","alpha_stand","alpha_sitstand","alpha_ground_pick",
               "roulade","ball_kick_left","ball_kick_right","roller","roller_crouch") {
  curl.exe -s -L -o "policies\$n.onnx" "$base/$n.onnx"
}
```

Что каждая делает:

| Файл | Поведение |
|---|---|
| `alpha_walking.onnx` | ходьба по командам скорости (вперёд/назад, стрейф, поворот) |
| `alpha_stand.onnx` | стоять + команды позы корпуса (смещения и наклоны) |
| `alpha_sitstand.onnx` | сесть / встать одной политикой |
| `alpha_ground_pick.onnx` | наклониться и коснуться «клювом» пола |
| `roulade.onnx` | кувырок вперёд |
| `ball_kick_left/right.onnx` | удар по мячу |
| `roller.onnx`, `roller_crouch.onnx` | роликовые «коньки» под стопами |

## 6. Запуск симулятора

Все команды — из папки `microduck_rl` (скрипт читает сцены по относительным путям).

**Базовый запуск — ходьба + стояние:**

```powershell
uv run python ..\code\infer_policy_windows.py `
  --walking ..\policies\alpha_walking.onnx `
  --standing ..\policies\alpha_stand.onnx `
  --new-cmd-obs
```

Ожидаемый результат: открывается окно MuJoCo, утка встаёт из позы SIT и стоит.
Держите стрелку **вверх** — она пойдёт вперёд; отпустите (SPACE) — переключится на
политику стояния. Команды можно набирать **и в терминале, и прямо в окне MuJoCo**
(Windows-версия слушает оба источника).

**Полный набор (все трюки в одной сессии):**

```powershell
uv run python ..\code\infer_policy_windows.py `
  --walking ..\policies\alpha_walking.onnx `
  --standing ..\policies\alpha_stand.onnx `
  --sitstand ..\policies\alpha_sitstand.onnx `
  --ground-pick ..\policies\alpha_ground_pick.onnx `
  --roulade ..\policies\roulade.onnx `
  --kick-left ..\policies\ball_kick_left.onnx `
  --kick-right ..\policies\ball_kick_right.onnx `
  --new-cmd-obs
```

**Ролики (другой корпус — пассивные колёса под стопами):**

```powershell
uv run python ..\code\infer_policy_windows.py `
  --walking ..\policies\roller.onnx `
  --standing ..\policies\roller_crouch.onnx `
  --roller --new-cmd-obs
```

**Смоук-тест без рук** — утка 20 секунд шагает вперёд и выходит сама (флаг добавлен в
Windows-копию):

```powershell
uv run python ..\code\infer_policy_windows.py `
  --walking ..\policies\alpha_walking.onnx --new-cmd-obs `
  --lin-vel-x 0.15 --auto-quit 20
```

### 6.1 GUI с кнопками в окне MuJoCo

Стандартный viewer MuJoCo не отдаёт события мыши в Python, поэтому для кнопок написан
собственный GLFW-рендер: `code/infer_policy_gui.py`. Внизу окна — панель кнопок:

```
[Поворот ◀] [◀ Влево] [▲ Вперёд] [СТОП] [▼ Назад] [Вправо ▶] [Поворот ▶]
```

Кнопки работают **как тумблер**: нажал — утка едет в этом направлении, нажал ещё раз —
останавливается (можно одновременно держать несколько: вперёд + поворот = едет по дуге).
«СТОП» сбрасывает все команды. То же самое — клавишами (W/S/A/D/стрелки, Q/E — поворот,
SPACE — стоп).

```powershell
uv pip install glfw PyOpenGL    # один раз (Pillow уже есть)

uv run python ..\code\infer_policy_gui.py `
  --walking ..\policies\alpha_walking.onnx `
  --standing ..\policies\alpha_stand.onnx `
  --new-cmd-obs
```

Можно добавить и трюковые политики (`--sitstand`, `--ground-pick`, `--roulade`,
`--kick-left/right` — все требуют `--new-cmd-obs`), они вешаются на клавиши Y/G/R/K/L.

Управление в GUI:

| Действие | Как |
|---|---|
| Ехать | клик по кнопке (клик ещё раз — стоп); СТОП сбрасывает всё |
| Камера: орбита | зажать ПКМ и тянуть |
| Камера: зум | колесо мыши |
| Клавиши | W/S/A/D или стрелки — движение, Q/E — поворот, SPACE — стоп |
| Доп. клавиши | Y сесть/встать, G наклон, K/L удары, R кувырок, P толчок, T пауза политики |
| Выход | ESC или закрыть окно |

Три технических момента (зафиксированы в коде):
- **физика и рендер в разных потоках**: политики рассчитаны на цикл 50 Гц, а `mjr_render`
  на офисном GPU занимает 60-100 мс на кадр (отражённый пол + тени) — инлайн-рендер давал
  real-time 0.08x и утка не могла ходить. Теперь политика/физика живут в своём потоке
  (0.96x real-time), рендер не отнимает у неё время; отражения и тени в UI отключены
  (переключатель `scn.flags` и `shadowsize=0`);
- после `mjr_render` MuJoCo оставляет включёнными `GL_DEPTH_TEST`/`GL_CULL_FACE`/`GL_LIGHTING` —
  с включённым освещением `glColor` уходит в материал и кнопки рендерятся чёрными, поэтому
  перед оверлеем состояние сбрасывается (`glUseProgram(0)` + отключение фиксированного конвейера);
- подписи кнопок отрисовываются в текстуры через Pillow (шрифт Segoe UI); текстуры грузятся
  построчно снизу вверх, поэтому текстурные координаты квадов инвертированы по V — иначе
  подписи читаются «вверх ногами».

`--selftest` прогоняет кнопки программно (вперёд 2-5 с, поворот 6-9 с, выход) — удобно
проверять без рук; `--screenshot file.png` сохраняет кадр через 1 с и выходит.

## 7. Управление

| Клавиша | Действие |
|---|---|
| ↑ / ↓ | вперёд / назад (команда `lin_vel_x`) |
| ← / → | стрейф влево / вправо (`lin_vel_y`); в режиме роликов — поворот |
| A / E | поворот влево / вправо (`ang_vel_z`) |
| SPACE | сброс всех команд скорости |
| T | пауза инференса (моторы держат последнюю цель) |
| G | наклон «клювом» к полу (нужна `--ground-pick`) |
| Y | сесть / встать (нужна `--sitstand` или `--slope`) |
| K / L | удар левой / правой ногой (нужны `--kick-*`) |
| R | кувырок (нужна `--roulade`) |
| P | случайный толчок корпуса (1 м/с) — проверка рефлексов |
| B | режим позы корпуса: ↑/↓ Δz, ←/→ Δpitch, A/E Δroll, Z/S Δyaw |
| H | режим головы: Z/S шея, ↑/↓ pitch, ←/→ yaw, A/E roll |
| Q | выход |

Полезно смотреть: каждую секунду терминал печатает `[vel 1s avg]` — достигнутая скорость
тела против команды (например `fwd=+0.11/+0.30` — команда 0.30 м/с, едет 0.11 м/с) и
высоту корпуса в мм. По этой строке видно, что политика реально отслеживает команды.

## 8. Что под капотом (кратко)

- **Наблюдение 61-D:** угловая скорость корпуса (3) + проекция гравитации (3) +
  позиции суставов (14) + скорости (14) + прошлое действие (14) +
  команды (13 = twist 3 + поза головы 4 + поза корпуса 6). Поэтому флаг `--new-cmd-obs`.
- **BAM-актуаторы:** сервы XL330 моделируются не идеальным PD-регулятором, а моделью
  BAM — напряжение, противоЭДС, трение, просадка батареи. Именно это закрывает разрыв
  sim2real для маленького робота. `--no-bam` — отключить и сравнить.
- **Hot-swap политик:** все политики обучены с общим контрактом наблюдений, поэтому
  скрипт переключает их «на лету» (ходьба ↔ стояние по величине команды, Y/K/L/R — эпизоды).
- **50 Гц:** шаг физики 0.005 с, инференс каждые 4 шага (decimation 4).

Эксперименты-«потыкать»:

```powershell
--debug          # печать наблюдений и действий каждые 50 шагов
--save-csv out.csv   # записать obs/action всех шагов
--vin 6.0 --vin-drop-gain 0.2   # «подсевшая батарея» — как меняется походка
--no-bam         # идеальные PD-актуаторы вместо BAM
--delay 2 5      # задержка команд, как на реальном UART-шлейфе
```

## 9. Windows-адаптация

Оригинальный `infer_policy.py` — POSIX-only (читает клавиатуру через `termios`/`select`
и падает на импорте в Windows) и слушает клавиши только из терминала. В
`code/infer_policy_windows.py` изменено:

1. импорты `termios`/`tty`/`select` → `msvcrt`;
2. класс `TerminalInput` переписан на `msvcrt.kbhit()`/`getwch()` (стрелки приходят
   парами `\x00`/`\xe0` + сканкод);
3. **клавиши принимаются и из окна MuJoCo** — через `key_callback` у
   `mujoco.viewer.launch_passive` обе очереди слиты в одну thread-safe очередь
   (оригинал читал только терминал, и нажатия в окне «терялись»);
4. stdout принудительно переведён в UTF-8 — иначе на русской локали (cp1251) скрипт
   падает на символе `Δ` при печати справки;
5. добавлен флаг `--auto-quit N` для автотестов.

Остальной код идентичен оригиналу. Diff можно посмотреть:

```powershell
git --no-pager diff --no-index microduck_rl\scripts\infer_policy.py code\infer_policy_windows.py
```

## 10. Следующий шаг: полный симулятор (`robotd --sim` + `duck-body`)

То, что мы запустили, — инференс политик в MuJoCo. У Microduck есть и «честный» симулятор,
где работают **настоящие демоны с робота** (тот же `robotd`, тот же цикл 50 Гц, IPC,
`robotctl`), а MuJoCo-процесс (`duck-body`) лишь заменяет шину сервоприводов по TCP:

```sh
scripts/duck-sim              # утка в MuJoCo, которой управляет настоящий robotd
scripts/duck-sim drive        # проехать вперёд 8 секунд
scripts/duck-sim ctl health   # robotctl, направленный на утку
```

Это требует Linux (WSL2 подойдёт): Rust toolchain для сборки демонов, Python 3.12 для
`duck-body` и `libonnxruntime`. Подробности: `microduck/docs/robot/simulation.md`.
В отдельном уроке разберём сборку и запуск этого пути.

## 11. Ссылки

- [microduck (наш форк)](https://github.com/GeBondar/microduck) / [оригинал](https://github.com/pollen-robotics/microduck)
- [microduck_rl](https://github.com/pollen-robotics/microduck_rl)
- [Набор политик на Hugging Face](https://huggingface.co/pollen-robotics/microduck-policies)
- [Документация симуляции](https://github.com/pollen-robotics/microduck/blob/main/docs/robot/simulation.md)
- [Как устроен робот](https://github.com/pollen-robotics/microduck/blob/main/docs/design/architecture.md)
