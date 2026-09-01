#Requires AutoHotkey v2.0
#SingleInstance Off
#NoTrayIcon
CoordMode("Mouse", "Screen")

if A_Args.Length < 12
    ExitApp(2)

targetHwnd := Integer(A_Args[1])
startX := Integer(A_Args[2])
startY := Integer(A_Args[3])
buttonLeft := Integer(A_Args[4])
buttonTop := Integer(A_Args[5])
buttonRight := Integer(A_Args[6])
buttonBottom := Integer(A_Args[7])
taskbarLeft := Integer(A_Args[8])
taskbarTop := Integer(A_Args[9])
taskbarRight := Integer(A_Args[10])
taskbarBottom := Integer(A_Args[11])
shellPid := Integer(A_Args[12])

RestorePointer(*) {
    global startX, startY
    MouseMove(startX, startY, 0)
}
OnExit(RestorePointer)

if !WinExist("ahk_id " targetHwnd) || WinGetMinMax("ahk_id " targetHwnd) != -1
    ExitApp(4)
MouseGetPos(&currentX, &currentY)
if Abs(currentX - startX) > 5 || Abs(currentY - startY) > 5
    ExitApp(3)

excludedClasses := Map(
    "Shell_TrayWnd", true,
    "Shell_SecondaryTrayWnd", true,
    "Progman", true,
    "WorkerW", true
)

; Windows 11 places taskbar previews above the bottom taskbar. Keep X fixed
; and walk upward in 75-pixel increments until the preview owns the point.
Loop 40 {
    nextX := startX
    nextY := startY - A_Index * 75
    MouseMove(nextX, nextY, 0)
    ; Give the taskbar preview host time to update hit-testing as the pointer
    ; crosses from the icon into the thumbnail.
    Sleep(35)
    MouseGetPos(&actualX, &actualY, &hoverHwnd)
    if Abs(actualX - nextX) > 3 || Abs(actualY - nextY) > 3
        ExitApp(5)
    if !hoverHwnd
        continue
    rootHwnd := DllCall("GetAncestor", "Ptr", hoverHwnd, "UInt", 2, "Ptr")
    if !rootHwnd
        continue
    try {
        rootPid := WinGetPID("ahk_id " rootHwnd)
        rootClass := WinGetClass("ahk_id " rootHwnd)
        WinGetPos(, , &rootWidth, &rootHeight, "ahk_id " rootHwnd)
    } catch {
        continue
    }
    if rootPid != shellPid || excludedClasses.Has(rootClass)
        continue
    if rootWidth < 96 || rootHeight < 48
        continue
    if !WinExist("ahk_id " targetHwnd) || WinGetMinMax("ahk_id " targetHwnd) != -1
        ExitApp(4)
    ; Deliberately rest on the thumbnail before clicking. Explorer's preview
    ; host can lag behind the visible animation on some Windows 11 systems.
    Sleep(400)
    MouseGetPos(, , &confirmedHwnd)
    confirmedRoot := confirmedHwnd
        ? DllCall("GetAncestor", "Ptr", confirmedHwnd, "UInt", 2, "Ptr")
        : 0
    if confirmedRoot != rootHwnd
        continue
    Click()
    ; Let Explorer process the click before OnExit returns the pointer.
    Sleep(300)
    ExitApp(0)
}

ExitApp(6)
