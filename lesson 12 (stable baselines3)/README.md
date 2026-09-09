# Урок 12. Stable Baselines 3: обучение с подкреплением

Цель урока - понять основы обучения с подкреплением (RL) и научиться обучать агентов библиотекой Stable Baselines 3 в стандартных средах Gymnasium и в собственной среде мобильного робота.

## Материалы

| Шаг | Статья | Результат |
|---:|---|---|
| 1 | [Введение в SB3](sb3_introduction.md) | PPO решает CartPole-v1 на 500/500 |
| 2 | [Своя среда мобильного робота](custom_robot_environment.md) | PPO довозит робота до цели, объезжая препятствия |

## Установка

```bash
pip install stable-baselines3 gymnasium matplotlib pillow tensorboard
```

## Код примеров

| Скрипт | Что делает |
|---|---|
| `code/01_cartpole/train_cartpole.py` | Обучает PPO на CartPole-v1, сохраняет модель и кривую обучения |
| `code/01_cartpole/evaluate_cartpole.py` | Демонстрация модели: анимация и кадры эпизода |
| `code/01_cartpole/draw_rl_loop.py` | Рисует схему цикла RL |
| `code/02_robot_env/robot_env.py` | Среда `RobotReacherEnv` + проверка случайными действиями |
| `code/02_robot_env/train_robot.py` | Обучает PPO в собственной среде |
| `code/02_robot_env/evaluate_robot.py` | Траектории обученной и случайной политик, анимация |
| `code/02_robot_env/draw_env_scheme.py` | Рисует схему среды |

## Запуск примеров

```bash
cd "lesson 12 (stable baselines3)/code/01_cartpole"
python train_cartpole.py
python evaluate_cartpole.py

cd ../02_robot_env
python robot_env.py
python train_robot.py
python evaluate_robot.py
```

Модели сохраняются в `models/`, логи TensorBoard — в `logs/`, картинки для статей — в `images/` (папки `models/` и `logs/` в git не попадают).

## После урока

Вернитесь к [уроку 10](<../lesson 10 (turtlebot3 sim)/README.md>) и попробуйте подключить обученную политику к TurtleBot3 в Gazebo: публикуйте действия в `cmd_vel`, а наблюдение формируйте из `/odom` и `/scan`.
