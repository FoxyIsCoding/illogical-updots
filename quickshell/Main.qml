//@ pragma UseQApplication
//@ pragma Env QT_QUICK_CONTROLS_STYLE=Basic

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import Quickshell
import Quickshell.Wayland
import Quickshell.Io

ApplicationWindow {
    id: statusWidget
    visible: true
    title: "Illogical Updots"
    
    width: 340
    height: 160
    
    minimumWidth: 340
    minimumHeight: 160
    maximumWidth: 340
    maximumHeight: 160

    color: "transparent"
    flags: Qt.Window | Qt.FramelessWindowHint

    property var m3colors: ({
        background: "#1a1112",
        surface: "#1a1112",
        surface_container: "#261d1e",
        on_surface: "#f0dedf",
        on_surface_variant: "#d7c1c3",
        primary: "#ffb2bc",
        outline: "#524345",
        primary_container: "#72333e",
        on_primary_container: "#ffd9dd",
        success: "#a3be8c"
    })

    function applyColors(content) {
        try {
            let data = JSON.parse(content);
            let newColors = {};
            for (let key in data) {
                newColors[key] = data[key];
            }
            newColors.success = "#a3be8c";
            m3colors = newColors;
        } catch (e) {}
    }

    FileView {
        id: colorLoader
        path: Quickshell.env("HOME") + "/.local/state/quickshell/user/generated/colors.json"
        watchChanges: true
        onFileChanged: {
            this.reload()
        }
        onLoadedChanged: {
            if (loaded) {
                statusWidget.applyColors(this.text())
            }
        }
    }

    MouseArea {
        anchors.fill: parent
        property point lastMousePos
        onPressed: (mouse) => { lastMousePos = Qt.point(mouse.x, mouse.y) }
        onPositionChanged: (mouse) => {
            let dx = mouse.x - lastMousePos.x
            let dy = mouse.y - lastMousePos.y
            statusWidget.x += dx
            statusWidget.y += dy
        }
    }

    Rectangle {
        anchors.fill: parent
        color: statusWidget.m3colors.surface
        radius: 16
        border.color: statusWidget.m3colors.outline
        border.width: 1
        
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 12
            
            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                
                Rectangle {
                    width: 32
                    height: 32
                    radius: 8
                    color: statusWidget.m3colors.primary_container
                    
                    Image {
                        anchors.centerIn: parent
                        source: "image://icon/illogical-updots"
                        width: 20
                        height: 20
                        fillMode: Image.PreserveAspectFit
                        onStatusChanged: {
                            if (status === Image.Error) {
                                source = "file:///usr/share/icons/hicolor/256x256/apps/illogical-updots.png"
                            }
                        }
                    }
                }
                
                ColumnLayout {
                    spacing: 0
                    Label {
                        text: "Illogical Updots"
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                        color: statusWidget.m3colors.on_surface
                    }
                    Label {
                        text: "System Sync Utility"
                        font.pixelSize: 12
                        color: statusWidget.m3colors.on_surface_variant
                    }
                }
                
                Item { Layout.fillWidth: true }
                
                Rectangle {
                    width: 28
                    height: 28
                    radius: 14
                    color: "transparent"
                    Label {
                        anchors.centerIn: parent
                        text: "×"
                        font.pixelSize: 20
                        color: statusWidget.m3colors.on_surface_variant
                    }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: statusWidget.close()
                    }
                }
            }
            
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: statusWidget.m3colors.surface_container
                radius: 12
                
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 12
                    
                    Rectangle {
                        width: 8
                        Layout.fillHeight: true
                        radius: 4
                        color: statusWidget.m3colors.success
                    }
                    
                    ColumnLayout {
                        spacing: 4
                        Label {
                            text: "Up to Date"
                            font.pixelSize: 14
                            font.weight: Font.Medium
                            color: statusWidget.m3colors.success
                        }
                        Label {
                            text: "~/dotfiles"
                            font.pixelSize: 12
                            font.family: "JetBrainsMono Nerd Font"
                            color: statusWidget.m3colors.on_surface_variant
                            elide: Text.ElideRight
                            Layout.preferredWidth: 160
                        }
                    }
                    
                    Item { Layout.fillWidth: true }
                    
                    Rectangle {
                        id: updateButton
                        Layout.preferredWidth: 80
                        Layout.preferredHeight: 32
                        radius: 16
                        color: statusWidget.m3colors.primary
                        
                        Label {
                            anchors.centerIn: parent
                            text: "Update"
                            font.pixelSize: 13
                            font.weight: Font.Medium
                            color: statusWidget.m3colors.background
                        }
                        
                        MouseArea {
                            anchors.fill: parent
                            onClicked: console.log("Update triggered")
                        }
                    }
                }
            }
        }
    }
}
