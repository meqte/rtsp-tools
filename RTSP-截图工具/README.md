# RTSP视频流截图工具

这是一个使用C++、Qt和OpenCV开发的简单RTSP视频流截图工具。该工具支持编译为独立的可执行文件，无需安装额外的依赖库即可在任何Windows设备上运行。

## 功能特点

- 提供四个输入框用于输入RTSP视频流地址
- 一键截图功能，可同时对多个视频流进行截图
- 截图以最高质量保存为JPG格式
- 截图自动保存在程序同一目录下，按顺序命名为1.jpg、2.jpg等
- 支持编译为独立的可执行文件，无需安装额外依赖

## 构建要求（开发环境）

- CMake 3.5+
- Qt 5.x
- OpenCV 4.x
- Visual Studio 2019或更高版本（推荐使用MSVC编译器）

## 构建步骤

### 普通构建

1. 确保已安装所需的依赖项：Qt和OpenCV
2. 创建构建目录：
   ```
   mkdir build
   cd build
   ```
3. 配置并构建项目：
   ```
   cmake ..
   cmake --build .
   ```

### 构建独立可执行文件

1. 确保已安装所需的依赖项：Qt和OpenCV
2. 创建构建目录：
   ```
   mkdir build
   cd build
   ```
3. 配置并构建项目（使用MSVC编译器）：
   ```
   cmake .. -G "Visual Studio 16 2019" -A Win32
   cmake --build . --config Release
   ```
4. 生成的可执行文件将位于`build\Release`目录下，包含所有必要的依赖项

## 使用说明

1. 在输入框中输入RTSP地址，例如：`rtsp://admin:password@192.168.1.100:554/stream`
2. 点击「一键截图」按钮
3. 截图将保存在程序所在目录

## 部署说明

构建完成后，可以直接将生成的可执行文件及其同目录下的所有DLL文件复制到任何Windows设备上运行，无需安装额外的依赖库。