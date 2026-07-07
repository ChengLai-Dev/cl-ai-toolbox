# C++ 编码风格

1. **谨慎使用 `auto`**：变量声明优先写出完整类型名。迭代器（iterator / const_iterator）或类型名较长的情况可以使用 `auto`。
2. **优先类内初始化**：成员变量优先在类定义中给出初始值，仅在值依赖构造函数参数时才在构造函数中初始化。
3. **C++23 标准，C++11 风格**：CMake 配置为 C++23 标准（以便使用 `std::stacktrace`、`std::format` 等便利特性），但代码风格保持克制，不过度使用 C++11 以上的语法糖。若想使用 C++11以上 的高级特性（如 concepts、coroutines），必须先向开发者提问确认。
4. **优先使用库定义的类型**：当调用第三方库（如 OpenGL 等）返回库定义的类型（如 `GLuint`、`GLenum`）时，变量声明应使用该库类型而非底层原始类型（如 `unsigned int`），以保持语义清晰。
5. **杜绝魔数，优先使用库提供的命名常量**：调用第三方库函数传参时，若库已提供对应的命名常量（如 `STBI_rgb_alpha`、`GL_RGBA8` 等），必须使用命名常量而非直接写数值字面量。同理，项目中若有现成的枚举、常量或工具函数表达该语义，也应优先使用，保证代码自描述。

# 命名规则

1. **C++ 文件命名**：使用大驼峰（PascalCase），如 `Vec2.h`、`RawInput.cpp`、`PythonScriptApp.h`。
2. **C++ 函数命名**：使用大驼峰（PascalCase），如 `GetInstance()`、`LoadTexture()`、`BeginScene()`。
3. **Python 文件命名**：使用大驼峰（PascalCase），与 C++ 文件命名保持一致，如 `MenuScene.py`、`AiController.py`、`SpriteAnimator.py`。
4. **Python 函数和成员变量命名**：使用小写下划线（snake_case），如 `on_init()`、`on_update()`、`take_damage()`、`move_speed`、`frame_count`。
