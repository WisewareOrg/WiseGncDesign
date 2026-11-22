# `_rk4`, the extension rk4_test.py holds Rk4.hpp to its checks through, built beside this file.
pybind11_add_module(_rk4 "${CMAKE_CURRENT_LIST_DIR}/Rk4Module.cpp")
target_link_libraries(_rk4 PRIVATE wise_eigen)
target_include_directories(_rk4 PRIVATE "${FPRIME_PROJECT_ROOT}")
set_target_properties(_rk4 PROPERTIES LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_LIST_DIR}")
