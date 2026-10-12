param(
    [ValidateSet(':app:assembleDebug', ':app:assembleRelease', ':app:checkReleaseCsp', ':app:lintDebug')]
    [string]$Task = ':app:assembleDebug',
    [switch]$Online
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$toolsRoot = Join-Path $projectRoot '.android-tools'
$javaHomePath = (Resolve-Path (Join-Path $toolsRoot 'jdk\jdk-17.0.20.1+1')).Path
$gradleRoot = (Resolve-Path (Join-Path $toolsRoot 'gradle-dist\gradle-8.7')).Path
$androidHomePath = (Resolve-Path (Join-Path $toolsRoot 'android-home')).Path
$gradleHomePath = (Resolve-Path (Join-Path $toolsRoot 'gradle-home')).Path
$androidUserHomePath = Join-Path $env:USERPROFILE '.android'

# Reuse the existing debug key, so a locally rebuilt test package remains
# upgrade-compatible with the one already installed on the test phone.
if ($Task -eq ':app:assembleDebug' -and
    -not (Test-Path -LiteralPath (Join-Path $androidUserHomePath 'debug.keystore'))) {
    throw 'Existing Android debug.keystore not found; refusing to generate a different signing key.'
}

$env:JAVA_HOME = $javaHomePath
$env:ANDROID_HOME = $androidHomePath
$env:ANDROID_USER_HOME = $androidUserHomePath
$env:GRADLE_USER_HOME = $gradleHomePath

$java = Join-Path $javaHomePath 'bin\java.exe'
$launcher = Join-Path $gradleRoot 'lib\gradle-launcher-8.7.jar'
$agent = Join-Path $gradleRoot 'lib\agents\gradle-instrumentation-agent-8.7.jar'
$jvmArgs = @(
    '--add-opens=java.base/java.util=ALL-UNNAMED',
    '--add-opens=java.base/java.lang=ALL-UNNAMED',
    '--add-opens=java.base/java.lang.invoke=ALL-UNNAMED',
    '--add-opens=java.prefs/java.util.prefs=ALL-UNNAMED',
    '--add-opens=java.base/java.nio.charset=ALL-UNNAMED',
    '--add-opens=java.base/java.net=ALL-UNNAMED',
    '--add-opens=java.base/java.util.concurrent.atomic=ALL-UNNAMED',
    '-Xmx2g',
    '-Dfile.encoding=UTF-8',
    '-Duser.country=CN',
    '-Duser.language=zh',
    '-Duser.variant'
)

Push-Location $PSScriptRoot
try {
    # These JVM arguments match Gradle's required build VM exactly. Otherwise
    # --no-daemon still forks a disposable daemon, whose Windows pipe fails here.
    $gradleArgs = @('org.gradle.launcher.GradleMain', '--no-daemon')
    if (-not $Online) { $gradleArgs += '--offline' }
    $gradleArgs += $Task
    & $java @jvmArgs "-javaagent:$agent" '-cp' $launcher @gradleArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}
