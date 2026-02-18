cmake_minimum_required(VERSION 3.17)
project(RobotBackendCPP)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Dependencies
find_package(OpenCV REQUIRED)
# find_package(OnnxRuntime) # Uncomment when installed/configured

include_directories(${OpenCV_INCLUDE_DIRS})
include_directories(include)

# Source files
file(GLOB SOURCES "src/*.cpp")

# Executable
add_executable(robot_core ${SOURCES})

# Link libraries
target_link_libraries(robot_core ${OpenCV_LIBS}) 
# target_link_libraries(robot_core onnxruntime) # Uncomment later

message(STATUS "OpenCV library status:")
message(STATUS "    config: ${OpenCV_DIR}")
message(STATUS "    version: ${OpenCV_VERSION}")
message(STATUS "    libraries: ${OpenCV_LIBS}")
