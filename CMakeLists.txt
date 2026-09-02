cmake_minimum_required(VERSION 3.24)

project(machine-evolved-shellworker LANGUAGES CXX)

include(FetchContent)
find_package(Boost 1.65 REQUIRED CONFIG)
find_package(Threads REQUIRED)

FetchContent_Declare(
  bullet
  URL https://github.com/bulletphysics/bullet3/archive/45aa392a280d2020946f5ee112f73072bbab6001.tar.gz
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE
  # Populate the source without adopting Bullet's legacy project-wide build.
  SOURCE_SUBDIR cmake/machine-evolved-unused
)

FetchContent_MakeAvailable(bullet)

if(EXISTS "${bullet_SOURCE_DIR}/src/btLinearMathAll.cpp")
  # Newer source packages ship aggregation units for clients that need only
  # the core simulation. This path also supports the local pybullet cache.
  add_library(
    machine_evolved_bullet STATIC
    ${bullet_SOURCE_DIR}/src/btLinearMathAll.cpp
    ${bullet_SOURCE_DIR}/src/btBulletCollisionAll.cpp
    ${bullet_SOURCE_DIR}/src/btBulletDynamicsAll.cpp
  )
  target_include_directories(machine_evolved_bullet PUBLIC ${bullet_SOURCE_DIR}/src)
  set(MACHINE_EVOLVED_BULLET_TARGETS machine_evolved_bullet)
  set(MACHINE_EVOLVED_BULLET_LINK_TARGETS machine_evolved_bullet)
else()
  # Bullet 2.86.1 predates the aggregation units. Adopt just its source-library
  # subtree so demos, tests, OpenGL, extras, and Python bindings stay excluded.
  file(STRINGS "${bullet_SOURCE_DIR}/VERSION" BULLET_VERSION)
  set(BULLET_PHYSICS_SOURCE_DIR "${bullet_SOURCE_DIR}")
  set(BUILD_BULLET3 OFF)
  set(BUILD_SHARED_LIBS OFF)
  set(INSTALL_LIBS OFF)
  set(USE_DOUBLE_PRECISION OFF)
  add_subdirectory("${bullet_SOURCE_DIR}/src" "${bullet_BINARY_DIR}/src" EXCLUDE_FROM_ALL)
  set(MACHINE_EVOLVED_BULLET_TARGETS BulletDynamics BulletCollision LinearMath)
  set(MACHINE_EVOLVED_BULLET_LINK_TARGETS BulletDynamics BulletCollision LinearMath)
endif()

# Bullet 2.86's optional quick profiler keeps process-global bookkeeping that
# is unsafe when ShellWorker evaluates multiple independent worlds on parallel
# threads. Training does not consume those timing counters, so compile them out
# while retaining the physics code and strict floating-point settings.
foreach(bullet_target IN LISTS MACHINE_EVOLVED_BULLET_TARGETS)
  target_compile_definitions(${bullet_target} PUBLIC BT_NO_PROFILE=1)
endforeach()

set(MACHINE_WORKER_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/MachineWorker/MachineWorker")

add_executable(
  shellworker
  ShellWorker/ShellWorker.cpp
  ${MACHINE_WORKER_SOURCE_DIR}/AsyncCommunicator.cpp
  ${MACHINE_WORKER_SOURCE_DIR}/BulletCreature.cpp
  ${MACHINE_WORKER_SOURCE_DIR}/BulletInterface.cpp
  ${MACHINE_WORKER_SOURCE_DIR}/BulletWorkerBase.cpp
  ${MACHINE_WORKER_SOURCE_DIR}/Communicator.cpp
  ${MACHINE_WORKER_SOURCE_DIR}/CreatureBase.cpp
  ${MACHINE_WORKER_SOURCE_DIR}/CreatureStructure.cpp
  ${MACHINE_WORKER_SOURCE_DIR}/IMotorController.cpp
  ${MACHINE_WORKER_SOURCE_DIR}/LinearMotorController.cpp
  ${MACHINE_WORKER_SOURCE_DIR}/WorkEvaluator.cpp
)

target_compile_features(shellworker PRIVATE cxx_std_17)
target_compile_definitions(shellworker PRIVATE SHELL)
target_include_directories(
  shellworker
  PRIVATE
    ${MACHINE_WORKER_SOURCE_DIR}
    ${bullet_SOURCE_DIR}/src
    ${Boost_INCLUDE_DIRS}
)
target_link_libraries(shellworker PRIVATE ${MACHINE_EVOLVED_BULLET_LINK_TARGETS} Threads::Threads)

add_executable(
  replayworker
  ReplayWorker/ReplayWorker.cpp
  ${MACHINE_WORKER_SOURCE_DIR}/BulletCreature.cpp
  ${MACHINE_WORKER_SOURCE_DIR}/BulletInterface.cpp
  ${MACHINE_WORKER_SOURCE_DIR}/CreatureBase.cpp
  ${MACHINE_WORKER_SOURCE_DIR}/CreatureStructure.cpp
  ${MACHINE_WORKER_SOURCE_DIR}/IMotorController.cpp
  ${MACHINE_WORKER_SOURCE_DIR}/LinearMotorController.cpp
)
target_compile_features(replayworker PRIVATE cxx_std_17)
target_include_directories(
  replayworker
  PRIVATE
    ${MACHINE_WORKER_SOURCE_DIR}
    ${bullet_SOURCE_DIR}/src
    ${Boost_INCLUDE_DIRS}
)
target_link_libraries(replayworker PRIVATE ${MACHINE_EVOLVED_BULLET_LINK_TARGETS} Threads::Threads)

if(MSVC)
  target_compile_options(shellworker PRIVATE /W4)
  target_compile_options(replayworker PRIVATE /W4)
else()
  target_compile_options(shellworker PRIVATE -Wall -Wextra -Wpedantic)
  target_compile_options(replayworker PRIVATE -Wall -Wextra -Wpedantic)
  if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    # The recovered Visual Studio worker used strict floating-point evaluation
    # with SIMD extensions disabled. Preserve that numerical mode for parity.
    target_compile_options(shellworker PRIVATE -ffp-model=strict -ffp-contract=off -U__ARM_NEON__)
    target_compile_options(replayworker PRIVATE -ffp-model=strict -ffp-contract=off -U__ARM_NEON__)
    foreach(bullet_target IN LISTS MACHINE_EVOLVED_BULLET_TARGETS)
      target_compile_options(${bullet_target} PRIVATE -ffp-model=strict -ffp-contract=off -U__ARM_NEON__)
    endforeach()
  endif()
endif()
