### **Введение (обновлённое)**

URDF (Unified Robot Description Format) — основной формат описания роботов в ROS 2. Создание URDF-файла вручную может быть трудоёмким, особенно для сложных моделей. К счастью, сообщество разработало множество инструментов для его автоматического **экспорта из CAD-программ**, **конвертации из других форматов** и **визуальной проверки**. Этот туториал поможет вам сориентироваться в этом многообразии.

---

### **Часть 1: Экспорт URDF из CAD-систем**

Самый эффективный способ получить URDF для существующей механической конструкции — экспортировать его из программы, в которой создавалась 3D-модель. Вот наиболее популярные экспортёры для различных CAD-систем (все ссылки ведут на страницу документации ROS):

| CAD-система | Инструмент | Краткое описание |
| :--- | :--- | :--- |
| **Blender** | [Blender URDF Exporter](http://wiki.ros.org/sw_urdf_exporter) | Позволяет экспортировать модель, созданную в Blender, в формат URDF. |
| **CREO Parametric** | [CREO Parametric URDF Exporter](http://wiki.ros.org/sw_urdf_exporter) | Экспортёр для профессиональной CAD-системы от PTC. |
| **FreeCAD** | [FreeCAD ROS Workbench](https://wiki.freecad.org/RobotWorkbench) | Верстак (Workbench) в FreeCAD для робототехники, включает инструменты экспорта. |
| | [RobotCAD (FreeCAD OVERCROSS)](https://github.com/OVERCROSS-FreeCAD-Addons/RobotCAD) | Дополнение (аддон) для FreeCAD, расширяющее функционал экспорта роботов. |
| | [Freecad to Gazebo Exporter](https://github.com/FreeCAD/freecad.cadquery_gazebo) | Инструмент для экспорта моделей из FreeCAD в симулятор Gazebo. |
| **Fusion 360** | [Fusion 360 URDF Exporter](https://github.com/syuntoku14/fusion2urdf) | Один из самых популярных экспортёров для Fusion 360. |
| | [FusionSDF: Fusion 360 to SDF exporter](https://github.com/Adlink-ROS/urdf-fusion-sdf-exporter) | Экспортирует модель в формат SDF (используется в Ignition Gazebo). |
| **OnShape** | [OnShape URDF Exporter](https://cad.onshape.com/documents/6a4b9e1e8e4f7a7a6b3d2c1f/w/8e1a2b3c4d5e6f7a8b9c0d1e) | Экспортёр для облачной CAD-платформы OnShape. |
| **SolidWorks** | [SolidWorks URDF Exporter](http://wiki.ros.org/sw_urdf_exporter) | Классический и хорошо зарекомендовавший себя инструмент для SolidWorks. |
| **Универсальные** | [ExportURDF Library](https://github.com/robcog-iai/ExportURDF) | Библиотека, обещающая поддержку Fusion360, OnShape и Solidworks. |
| **Платформы** | [RoboForge Project](https://www.roboforge.dev/) | Проект, предлагающий как бесплатные, так и платные (freemium) инструменты для проектирования и экспорта роботов. |

> **Важно:** Эти инструменты разрабатываются и поддерживаются сообществом независимо от основных разработчиков ROS. Их работоспособность и удобство могут различаться, но они значительно ускоряют процесс.

**Общий принцип работы экспортёров:**
1.  Устанавливается плагин или скрипт для вашей CAD-программы.
2.  В модели назначаются **системы координат** для соединений (joints).
3.  Запускается функция экспорта, которая генерирует:
    *   Текстовый `.urdf` файл с описанием кинематики.
    *   Папку с сетчатыми моделями (`.stl`, `.dae`), которые будут использоваться для визуализации и коллизий.

---

### **Часть 2: Другие инструменты экспорта и конвертации**

Если у вас нет исходной CAD-модели, но есть файл в другом формате, или вы хотите перенести модель между симуляторами, вам помогут инструменты конвертации:

| Тип инструмента | Инструмент | Описание |
| :--- | :--- | :--- |
| **Конвертеры форматов** | [Gazebo SDFormat to URDF Parser](http://wiki.ros.org/sdformat_to_urdf) | Парсер для преобразования моделей из формата SDF (используется в Gazebo) в URDF. |
| | [SDF to URDF Converter in Python](https://github.com/andreasBihlmaier/sdf2urdf) | Простой Python-скрипт для конвертации SDF в URDF. |
| **Экспорт в симуляторы** | [URDF to Webots Simulator Format](https://www.cyberbotics.com/doc/reference/proto) | Документация по созданию прототипов (PROTO) в Webots, куда можно конвертировать URDF. |
| | [CoppeliaSim URDF Exporter](https://www.coppeliarobotics.com/helpFiles/en/urdfImportExport.htm) | Встроенная функция в CoppeliaSim для импорта/экспорта URDF. |
| | [Isaac Sim URDF Exporter](https://docs.omniverse.nvidia.com/app_isaacsim/app_isaacsim/tutorial_import_urdf.html) | Туториал по импорту URDF в симулятор NVIDIA Isaac Sim. |
| **Универсальные наборы** | [The Blender Robotics Tools](https://github.com/dfki-ric/blender_robotics_tools) | Репозиторий, включающий множество полезных инструментов для Blender, в том числе экспорт в URDF. |

---

### **Часть 3: Просмотр URDF и SDF файлов**

Прежде чем использовать URDF в симуляции или на реальном роботе, его нужно проверить. Инструменты визуализации позволяют сделать это быстро и удобно.

#### **Онлайн-просмотрщики (Web Viewers)**
Эти сервисы не требуют установки — просто перетащите файлы в браузер.
*   **URDF Viewer Example:** [gkjohnson.github.io/urdf-loaders/javascript/example/bundle/](https://gkjohnson.github.io/urdf-loaders/javascript/example/bundle/)
    *   Простой, работает перетаскиванием папки с URDF и meshes. Лучше в Chrome.
*   **Robot Viewer:** [viewer.robotsfan.com](https://viewer.robotsfan.com/)
    *   Поддерживает URDF, Xacro, MJCF. Позволяет кликать по модели и управлять суставами.
*   **Web Viewer for URDF Files:** [GitHub Репозиторий](https://github.com/gramaziokohler/urdf-viewer) и [живой веб-сайт](https://gramaziokohler.github.io/urdf-viewer/)
    *   Ещё один легковесный веб-просмотрщик с открытым исходным кодом.

#### **Просмотр в инструментах ROS и Jupyter**
Для более глубокой интеграции с экосистемой ROS:
*   **Просмотр SDF моделей в RViz:** [Инструкция](http://wiki.ros.org/sdformat_to_urdf/Tutorials/ViewSDFModelsInRviz)
    *   Несмотря на название, туториал объясняет, как сконвертировать SDF в URDF и затем просмотреть модель в стандартном визуализаторе ROS — RViz.
*   **Jupyterlab URDF Viewer:** [Jupyterlab ROS](https://github.com/robostudio/jupyterlab-ros)
    *   Расширение для JupyterLab, позволяющее визуализировать URDF-модели прямо в ваших ноутбуках (notebooks).

### **Заключение и практический совет**

1.  **Для экспорта:** Найдите в списке ваш CAD-инструмент и попробуйте установить соответствующий экспортёр.
2.  **Для конвертации:** Если у вас есть модель в SDF или для другого симулятора, используйте инструменты из Части 2.
3.  **Для просмотра:** Начните с **Robot Viewer** ([robotsfan.com](https://viewer.robotsfan.com/)) — он наиболее функционален для быстрой проверки. Если вам нужно встроить модель в документацию или отчёт, попробуйте **Jupyterlab URDF Viewer**.

Попробуйте экспортировать простую модель из вашей CAD-системы и загрузить её в один из просмотрщиков, чтобы сразу увидеть результат своей работы