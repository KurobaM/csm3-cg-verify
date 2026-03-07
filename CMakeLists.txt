cmake_minimum_required(VERSION 4.2)

project(csm3-cgv)

find_package(Python COMPONENTS Development)
if (NOT Python_FOUND)
  message(FATAL_ERROR "Python not found")
 endif()
message("Python_FOUND:${Python_FOUND}")
message("Python_VERSION:${Python_VERSION}")
message("Python_Development_FOUND:${Python_Development_FOUND}")
message("Python_LIBRARIES:${Python_LIBRARIES}")