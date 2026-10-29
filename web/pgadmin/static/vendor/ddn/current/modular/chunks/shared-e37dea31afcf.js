/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"shared-e37dea31afcf","version":"ddn-next-1","releaseHash":"4f601dab202a346b52c70ff1ec6bfdfb7c17ab3fbd59854e38cda422320d3131","dependencies":["shared-73905c5bd21c","shared-a1e32f51fc2a","shared-ebd47c4e1fef","shared-f98a38a4da4d"],"modules":[{"id":"standalone/src/brand.js","bytes":14269,"sha256":"f724aacf27a51e472b2bf3a379b8f76e5b743dae0e72ea94f09d86a797b5b6a9","dependencies":[]},{"id":"standalone/src/document-draft.js","bytes":2402,"sha256":"67a4df015afff265703e7452c14883a4cf39e73ad4a368d0bd9d379b3ce175c1","dependencies":[]},{"id":"standalone/src/menus.js","bytes":16745,"sha256":"ce930bf33c887606127ab8a93f3eb9a619ee4a27abd825bbb1fc61242051ed8b","dependencies":[]},{"id":"standalone/src/modular-shell.js","bytes":1624,"sha256":"3addca797d4a8b882f61d110fea31a836d63ffa7c200cd897c81f3a2711c6d59","dependencies":["standalone/src/shell.js","standalone/src/modular-loading.js","standalone/src/website-navigation.js"]},{"id":"standalone/src/shell.js","bytes":131514,"sha256":"bb8c93cf50dc0e4958e8e81b8522cbf53758cdae74ff315d072fa2924f8beb42","dependencies":["viewer/src/drawer.js","standalone/src/brand.js","viewer/src/ui-icons.js","model/src/index.js","viewer/src/ui-theme.js","viewer/src/dialogs.js","viewer/src/choice-field.js","standalone/src/document-draft.js","language/src/index.js","viewer/src/ui-commands.js","viewer/src/popout.js","standalone/src/menus.js","standalone/src/zip.js"]},{"id":"standalone/src/website-navigation.js","bytes":3472,"sha256":"5537440bdd5fb48888afcc660a5cc11be025783179ef4e1f460c65128f877357","dependencies":["viewer/src/ui-icons.js"]},{"id":"standalone/src/zip.js","bytes":3068,"sha256":"ea57c9d7236eaa3818e66fbfb5d7c56c42a19a6e8bbe0436a40e8c8166f9f79a","dependencies":[]}],"hash":"9d3a2c343e5d3d30f3bab6e1a1a30057c205086d96db9798bc7aa951ea787491"},{"standalone/src/brand.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ddnLogoDarkDataURL = exports.ddnLogoDataURL = void 0;
exports.ddnLogoDataURL = "data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0nMS4wJyBlbmNvZGluZz0ndXRmLTgnPz4KPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjE5LjQ1MiAxMzYuNzQ4IDEwMC4wMDAgOTIuOTkzIj4KICA8ZGVmcyBpZD0iZGVmczI0NiI+CiAgICA8bWFzayBpZD0iZ2Vhci1ob2xlIj4KICAgICAgPHJlY3Qgd2lkdGg9IjEwMCIgaGVpZ2h0PSIxMDAiIGZpbGw9IiNmZmZmZmYiIGlkPSJyZWN0MjU4MiIgeD0iMCIgeT0iMCIgLz4KICAgICAgPGNpcmNsZSBjeD0iNTAiIGN5PSI1MCIgcj0iMTgiIGZpbGw9IiMwMDAwMDAiIGlkPSJjaXJjbGUyNTg0IiAvPgogICAgPC9tYXNrPgogICAgPG1hc2sgaWQ9ImdlYXItaG9sZS05Ij4KICAgICAgPHJlY3Qgd2lkdGg9IjEwMCIgaGVpZ2h0PSIxMDAiIGZpbGw9IiNmZmZmZmYiIGlkPSJyZWN0MjU4Mi00IiB4PSIwIiB5PSIwIiAvPgogICAgICA8Y2lyY2xlIGN4PSI1MCIgY3k9IjUwIiByPSIxOCIgZmlsbD0iIzAwMDAwMCIgaWQ9ImNpcmNsZTI1ODQtNyIgLz4KICAgIDwvbWFzaz4KICA8L2RlZnM+CiAgPGcgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTcwMC41MTEwNyw1NjUwLjIyMjUpIj4KICAgIDxnIGlkPSJnMTY1My0yIiB0cmFuc2Zvcm09Im1hdHJpeCgwLjEzMDA0OTMxLDAsMCwwLjEyOTg5ODQzLDU1My4wOTMxLC01NzU3LjgyOTIpIiBzdHlsZT0iZmlsbDojZmZmZmZmO3N0cm9rZS13aWR0aDozODcuNzc7c3Ryb2tlLWRhc2hhcnJheTpub25lIj4KICAgICAgPGcgaWQ9Imc1MjkxIiBzdHlsZT0iZmlsbDojMGM3NWJkO2ZpbGwtb3BhY2l0eToxO3N0cm9rZS13aWR0aDozODcuNzciPgogICAgICAgIDxwYXRoIHN0eWxlPSJmaWxsOiMwYzc1YmQ7ZmlsbC1vcGFjaXR5OjE7c3Ryb2tlLXdpZHRoOjM4Ny43NztzdHJva2UtZGFzaGFycmF5Om5vbmUiIGQ9Im0gMTY0NS4wNzE4LDIxOTQuNTc1IGMgLTE3LjY3ODEsLTE0Ljc3MDYgLTU4Ljg1OTYsLTM3LjgyMSAtOTYuNjQ2NSwtNTQuMDk1NyAtMzEuMzE5NSwtMTMuNDg5MiAtNTUuMjMwMiwtMjUuMzU1NSAtNzAuNDQwNiwtMzQuOTU4IC01My41MTYzLC0zMy43ODUzIC04Ny45Njg0LC04My4zODU0IC0xMDIuMDk1MywtMTQ2Ljk4NDYgLTQuMjQ4OSwtMTkuMTI4OSAtNi4xMzkyLC02Mi4wMTc3IC0yLjczMzMsLTYyLjAxNzcgMS4xMzM2LDAgMy40NjQ0LDEuNjU2MiA1LjE3OTYsMy42ODA0IDEwLjY5MjgsMTIuNjE5MSA0MC42MzgxLDM3LjY5MjEgNjUuNzA3OCw1NS4wMTY3IDU0LjQyNzIsMzcuNjEyMSAxMTQuMTA0OCw2Ni4yOTU0IDE4Ny4zMzMsOTAuMDM5IDE2LjU0MjgsNS4zNjM4IDQ1LjY3NzcsMTQuODEyNyA2NC43NDQ0LDIwLjk5NzQgNDMuMTk0NSwxNC4wMTEzIDYwLjI3NTIsMjAuNzE5OCA5MC42NjY3LDM1LjYwOTkgMzQuNTIzMSwxNi45MTQzIDU5LjIwMjgsMzMuNDEwOSA4My4zMzMzLDU1LjcwMjIgOC42NjAxLDggMjcuODYxMiwyOS42MjExIDI2LjMwNTcsMjkuNjIxMSAtMC4zMDAxLDAgLTUuODAyMywtMS44MjE0IC0xMi4yMjcyLC00LjA0NzYgLTE0LjcxMTYsLTUuMDk3NSAtMzMuNTYzNCwtOS44NjQ1IC01MC43NDUyLC0xMi44MzE5IC0xOC40MDksLTMuMTc5NCAtNjcuNjIzNSwtMy4yMTczIC04Ny4wNDg3LC0wLjA2NyAtMjkuNTcyMiw0Ljc5NTggLTU4LjcxMTMsMTIuNTMwNSAtODUuMzMzNywyMi42NTEyIGwgLTEyLjM4MjQsNC43MDczIC0zLjYxNzYsLTMuMDIyNiB6IiBpZD0icGF0aDQyMi03LTUiIC8+CiAgICAgICAgPHBhdGggc3R5bGU9ImZpbGw6IzBjNzViZDtmaWxsLW9wYWNpdHk6MTtzdHJva2Utd2lkdGg6Mzg3Ljc3O3N0cm9rZS1kYXNoYXJyYXk6bm9uZSIgZD0ibSAxNDUyLjEyMDksMjI3MC4wNTI3IGMgLTM2Ljc0MDksLTExLjYyNSAtNjguMDM1MiwtMzAuMjExNyAtOTMuNDM5NSwtNTUuNDk2OCAtMTYuODgzOCwtMTYuODA0NSAtMjUuNTM0OSwtMjguMDE0NiAtMzUuNTE0MywtNDYuMDE5NSAtMTMuNDI1MSwtMjQuMjIxOCAtMjAuOTY5NCwtNDcuNzUzOCAtMjMuODYzMSwtNzQuNDMzOSAtMS41MDI2LC0xMy44NTQgLTAuODA2OCwtMjguODM0NiAxLjQwMjUsLTMwLjIwMDEgMC41ODYzLC0wLjM2MjMgNC41OTQyLDIuNDI5NCA4LjkwNjcsNi4yMDM3IDIwLjUzOTMsMTcuOTc1OCA0Ny4zMjgsMzUuODcxMiA2OS44NDEsNDYuNjU1MSAzMS41MjY4LDE1LjEwMTcgNTEuNTAwNywyMS43NTg2IDEwMy4zMzM0LDM0LjQzOTMgNDMuNjUzMiwxMC42Nzk2IDU4Ljg2NDcsMTUuNjkyMSA4My4xNjAxLDI3LjQwMjggMjMuNjMzMywxMS4zOTE0IDUwLjgzOTksMjguMzIyIDUwLjgzOTksMzEuNjM3NCAwLDEuNDggLTcwLjE2MzcsMzUuNzk3NiAtOTQuMjY5Niw0Ni4xMDgxIC0yMS4zODEsOS4xNDQ5IC00Mi4yNDAzLDE1Ljk0MjUgLTUxLjczMDQsMTYuODU3OCAtNC45NzM5LDAuNDc5NyAtOS43MTM4LC0wLjMyMTIgLTE4LjY2NjcsLTMuMTUzOSB6IiBpZD0icGF0aDQyMC01LTQiIC8+CiAgICAgICAgPHBhdGggc3R5bGU9ImZpbGw6IzBjNzViZDtmaWxsLW9wYWNpdHk6MTtzdHJva2Utd2lkdGg6Mzg3Ljc3O3N0cm9rZS1kYXNoYXJyYXk6bm9uZSIgZD0ibSAyMDE3LjEwNzMsMjQwMy44NjU3IGMgLTY2LjE2NjYsLTEyLjU1NjIgLTEyOS42OTUzLC00NC4zMjcyIC0yMDAuOTg2NCwtMTAwLjUxNDEgbCAtMTIsLTkuNDU3NiAtOS4zMzMzLC0wLjAyIGMgLTEyLjU4MDMsLTAuMDI4IC0zNy43MDgzLDQuMjI3NCAtNTgsOS44MjE1IC0yNi4zNzc0LDcuMjcxOCAtNTQuMzM4MSwxOC4zMjU1IC0xMDAuNjY2NywzOS43OTY2IC0yOS42NDY1LDEzLjczOTggLTQ5LjU2NzIsMjIuMzYwOCAtNTEuNjY5MiwyMi4zNjA4IC00LjQ1ODUsMCAtNjguOTk3NSwtNjkuOTI0MSAtNjguOTk3NSwtNzQuNzU0NyAwLC0wLjUxMDkgNS4yNSwtMy4xNzMzIDExLjY2NjcsLTUuOTE2NiA2LjQxNjcsLTIuNzQzMiAzMy44NjY3LC0xNS42NDcxIDYxLC0yOC42NzU0IDc5LjA3MDksLTM3Ljk2NjUgMTAxLjc0OTcsLTQ3LjE3NzYgMTM5LjMzMzMsLTU2LjU5MDggMzEuNDAzOCwtNy44NjU0IDQxLjk1NDIsLTkuMjMzIDcxLjMzMzQsLTkuMjQ2NSAzNS4zMDE1LC0wLjAxNiA1OS41Mzg3LDQuMjUxMiA5MS4xNTIzLDE2LjA0OTEgNzMuNjQ3OSwyNy40ODQ2IDEzMy41MjY5LDkyLjQzMDggMTQ0Ljc5NTMsMTU3LjA0ODUgMi44MDk0LDE2LjExMDIgMi41MTkyLDQzLjcwMzMgLTAuNDU1NCw0My4zMTA4IC0wLjQ1NDEsLTAuMDYgLTguMTgxNywtMS41MDQ5IC0xNy4xNzI1LC0zLjIxMTEgeiIgaWQ9InBhdGg0MTgtMy03NCIgLz4KICAgICAgICA8cGF0aCBzdHlsZT0iZmlsbDojMGM3NWJkO2ZpbGwtb3BhY2l0eToxO3N0cm9rZS13aWR0aDozODcuNzc7c3Ryb2tlLWRhc2hhcnJheTpub25lIiBkPSJtIDE1MTguNzg3NiwyNDQ1Ljc4NTQgYyAtMzUuNDYsLTMuNDQ3MyAtNzAuMjA1LC0xNS44MDk0IC05OS43ODk1LC0zNS41MDQ3IC0xNS45MjY2LC0xMC42MDI4IC0zOS4yMzQyLC0zMi42OTk1IC01MC45MzI3LC00OC4yODY5IC0yMS42NjAzLC0yOC44NjA3IC0zNi42NDQyLC02Ni4wODY0IC0zOC44MzI1LC05Ni40NzQ4IC0wLjczMDQsLTEwLjE0MzUgLTAuNTYyNCwtMTEuNjY2NiAxLjI4NzUsLTExLjY2NjYgMS4xNzAyLDAgOC4wMDksMy43MDkzIDE1LjE5NzMsOC4yNDMgMzguOTk4NywyNC41OTYzIDgwLjY2NTEsMzcuNzU2NSAxMjQuNzEwNiwzOS4zODk1IGwgMTkuNjQwOSwwLjcyODEgNy40NjA4LDkuOTEyNiBjIDMxLjQ0NzYsNDEuNzgyIDc2LjE0NDgsODQuOTY4NSAxMTkuODQ5MiwxMTUuNzk4NSBsIDkuMjU4NCw2LjUzMTEgLTcuOTI1MSwyLjQxMzMgYyAtMjYuMDk0Myw3Ljk0NTkgLTY5Ljc5NzQsMTEuODQ1OCAtOTkuOTI0OSw4LjkxNjkgeiIgaWQ9InBhdGg0MTYtNS00IiAvPgogICAgICAgIDxwYXRoIHN0eWxlPSJmaWxsOiMwYzc1YmQ7ZmlsbC1vcGFjaXR5OjE7c3Ryb2tlLXdpZHRoOjM4Ny43NztzdHJva2UtZGFzaGFycmF5Om5vbmUiIGQ9Im0gMTkwMS40NTQyLDI1MTguMzQzNCBjIC05NS4yMjE0LC0xMC4zMjI5IC0xOTYuNzg5MywtNTQuNzcyMyAtMjgzLjgwODQsLTEyNC4yMDM1IGwgLTkuMTY0OCwtNy4zMTI0IDIxLjgyLC0xMC42MjM4IGMgNDkuNTY0OCwtMjQuMTMyNCA2My45MDY3LC0zMC45MDEyIDc4LjY4MDMsLTM3LjEzNCA4LjUzOTksLTMuNjAyOSAxNS44NzcyLC02LjU1MDcgMTYuMzA1LC02LjU1MDcgMC40Mjc5LDAgNC44NDA3LDIuOTUyNiA5LjgwNjMsNi41NjEyIDIxLjExNjksMTUuMzQ2NCA1OC4yODY1LDM1LjY0NzQgODYuNDY4NCw0Ny4yMjY3IDYwLjQ3MTksMjQuODQ2NSAxNDAuMjIyLDQyLjIxMjEgMTkzLjg1NTMsNDIuMjEyMSA3LjM1NDIsMCAxMy4zNzEzLDAuMzYxNiAxMy4zNzEzLDAuODAzNiAwLDAuNDQxOSAtMi4zMzUyLDUuNzg2NyAtNS4xODkzLDExLjg3NzIgLTEyLjc0NTIsMjcuMTk3NSAtMzQuMDYwMiw1My4yNDgyIC01OS43MzAyLDczLjAwMDggbCAtOC4yMTEzLDYuMzE4NCAtMTguNDM0NiwtMC4xNDgyIGMgLTEwLjEzOTEsLTAuMDgyIC0yNi4yMzQ2LC0wLjk5MzkgLTM1Ljc2OCwtMi4wMjc0IHoiIGlkPSJwYXRoNDE0LTYtMyIgLz4KICAgICAgICA8cGF0aCBzdHlsZT0iZmlsbDojMGM3NWJkO2ZpbGwtb3BhY2l0eToxO3N0cm9rZS13aWR0aDozODcuNzc7c3Ryb2tlLWRhc2hhcnJheTpub25lIiBkPSJtIDE3MjguNzg3NiwyNTgwLjk1NDggYyAtNzMuMTczMywtMy4yNDA1IC0xMzcuOTYxMywtMjYuOTYyOSAtMTg0LC02Ny4zNzIyIC0xMy45Njk5LC0xMi4yNjE3IC0zMC42NjY4LC0zMS43MDQxIC0zMC42NjY4LC0zNS43MDk1IDAsLTAuNTE3MyA5Ljk5NjYsLTEuMzUwMyAyMi4yMTQ3LC0xLjg1MTEgMzYuMTI2MywtMS40ODA3IDcxLjMxOTIsLTYuOTE3OSAxMDQuMzkzOSwtMTYuMTI4NyBsIDE2LjYwODYsLTQuNjI1MiAxMi4wNTgyLDcuNzM0MiBjIDE5LjYwOTcsMTIuNTc3OCAyNy40NDE4LDE3LjA0MDcgNDYuOTE4NiwyNi43MzQ4IDU3Ljc4MzMsMjguNzYwNiAxMTcuNDU3MSw0Ni42Njg5IDE3NC4yOTY4LDUyLjMwNzIgOS4yNjU1LDAuOTE5MSAxNi4zNjIxLDIuMTU1MyAxNS43NzAyLDIuNzQ3MSAtMS44MzI5LDEuODMyOCAtMjUuOTEwOSwxMS4yODU0IC00My4xNjA5LDE2Ljk0NDEgLTMyLjA3MzgsMTAuNTIxNiAtNjMuMTc5OSwxNi40ODI0IC05Ny43NDM5LDE4LjczMDcgLTExLjcyMDgsMC43NjI0IC0yMi44MjA4LDEuMjcwNiAtMjQuNjY2NywxLjEyOTMgLTEuODQ1OCwtMC4xNDEzIC03LjI1NjEsLTAuNDI5NiAtMTIuMDIyNywtMC42NDA3IHoiIGlkPSJwYXRoNDEyLTItMDciIC8+CiAgICAgIDwvZz4KICAgIDwvZz4KICA8L2c+Cjwvc3ZnPgo=";
exports.ddnLogoDarkDataURL = "data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0nMS4wJyBlbmNvZGluZz0ndXRmLTgnPz4KPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjE5LjQ1MiAxMzYuNzQ4IDEwMC4wMDAgOTIuOTkzIj4KICA8ZGVmcyBpZD0iZGVmczI0NiI+CiAgICA8bWFzayBpZD0iZ2Vhci1ob2xlIj4KICAgICAgPHJlY3Qgd2lkdGg9IjEwMCIgaGVpZ2h0PSIxMDAiIGZpbGw9IiMwYzc1YmQiIGlkPSJyZWN0MjU4MiIgeD0iMCIgeT0iMCIgLz4KICAgICAgPGNpcmNsZSBjeD0iNTAiIGN5PSI1MCIgcj0iMTgiIGZpbGw9IiMwYzc1YmQiIGlkPSJjaXJjbGUyNTg0IiAvPgogICAgPC9tYXNrPgogICAgPG1hc2sgaWQ9ImdlYXItaG9sZS05Ij4KICAgICAgPHJlY3Qgd2lkdGg9IjEwMCIgaGVpZ2h0PSIxMDAiIGZpbGw9IiMwYzc1YmQiIGlkPSJyZWN0MjU4Mi00IiB4PSIwIiB5PSIwIiAvPgogICAgICA8Y2lyY2xlIGN4PSI1MCIgY3k9IjUwIiByPSIxOCIgZmlsbD0iIzBjNzViZCIgaWQ9ImNpcmNsZTI1ODQtNyIgLz4KICAgIDwvbWFzaz4KICA8L2RlZnM+CiAgPGcgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTcwMC41MTEwNyw1NjUwLjIyMjUpIj4KICAgIDxnIGlkPSJnMTY1My0yIiB0cmFuc2Zvcm09Im1hdHJpeCgwLjEzMDA0OTMxLDAsMCwwLjEyOTg5ODQzLDU1My4wOTMxLC01NzU3LjgyOTIpIiBzdHlsZT0iZmlsbDojMGM3NWJkO3N0cm9rZS13aWR0aDozODcuNzc7c3Ryb2tlLWRhc2hhcnJheTpub25lIj4KICAgICAgPGcgaWQ9Imc1MjkxIiBzdHlsZT0iZmlsbDojZmZmZmZmO2ZpbGwtb3BhY2l0eToxO3N0cm9rZS13aWR0aDozODcuNzciPgogICAgICAgIDxwYXRoIHN0eWxlPSJmaWxsOiNmZmZmZmY7ZmlsbC1vcGFjaXR5OjE7c3Ryb2tlLXdpZHRoOjM4Ny43NztzdHJva2UtZGFzaGFycmF5Om5vbmUiIGQ9Im0gMTY0NS4wNzE4LDIxOTQuNTc1IGMgLTE3LjY3ODEsLTE0Ljc3MDYgLTU4Ljg1OTYsLTM3LjgyMSAtOTYuNjQ2NSwtNTQuMDk1NyAtMzEuMzE5NSwtMTMuNDg5MiAtNTUuMjMwMiwtMjUuMzU1NSAtNzAuNDQwNiwtMzQuOTU4IC01My41MTYzLC0zMy43ODUzIC04Ny45Njg0LC04My4zODU0IC0xMDIuMDk1MywtMTQ2Ljk4NDYgLTQuMjQ4OSwtMTkuMTI4OSAtNi4xMzkyLC02Mi4wMTc3IC0yLjczMzMsLTYyLjAxNzcgMS4xMzM2LDAgMy40NjQ0LDEuNjU2MiA1LjE3OTYsMy42ODA0IDEwLjY5MjgsMTIuNjE5MSA0MC42MzgxLDM3LjY5MjEgNjUuNzA3OCw1NS4wMTY3IDU0LjQyNzIsMzcuNjEyMSAxMTQuMTA0OCw2Ni4yOTU0IDE4Ny4zMzMsOTAuMDM5IDE2LjU0MjgsNS4zNjM4IDQ1LjY3NzcsMTQuODEyNyA2NC43NDQ0LDIwLjk5NzQgNDMuMTk0NSwxNC4wMTEzIDYwLjI3NTIsMjAuNzE5OCA5MC42NjY3LDM1LjYwOTkgMzQuNTIzMSwxNi45MTQzIDU5LjIwMjgsMzMuNDEwOSA4My4zMzMzLDU1LjcwMjIgOC42NjAxLDggMjcuODYxMiwyOS42MjExIDI2LjMwNTcsMjkuNjIxMSAtMC4zMDAxLDAgLTUuODAyMywtMS44MjE0IC0xMi4yMjcyLC00LjA0NzYgLTE0LjcxMTYsLTUuMDk3NSAtMzMuNTYzNCwtOS44NjQ1IC01MC43NDUyLC0xMi44MzE5IC0xOC40MDksLTMuMTc5NCAtNjcuNjIzNSwtMy4yMTczIC04Ny4wNDg3LC0wLjA2NyAtMjkuNTcyMiw0Ljc5NTggLTU4LjcxMTMsMTIuNTMwNSAtODUuMzMzNywyMi42NTEyIGwgLTEyLjM4MjQsNC43MDczIC0zLjYxNzYsLTMuMDIyNiB6IiBpZD0icGF0aDQyMi03LTUiIC8+CiAgICAgICAgPHBhdGggc3R5bGU9ImZpbGw6I2ZmZmZmZjtmaWxsLW9wYWNpdHk6MTtzdHJva2Utd2lkdGg6Mzg3Ljc3O3N0cm9rZS1kYXNoYXJyYXk6bm9uZSIgZD0ibSAxNDUyLjEyMDksMjI3MC4wNTI3IGMgLTM2Ljc0MDksLTExLjYyNSAtNjguMDM1MiwtMzAuMjExNyAtOTMuNDM5NSwtNTUuNDk2OCAtMTYuODgzOCwtMTYuODA0NSAtMjUuNTM0OSwtMjguMDE0NiAtMzUuNTE0MywtNDYuMDE5NSAtMTMuNDI1MSwtMjQuMjIxOCAtMjAuOTY5NCwtNDcuNzUzOCAtMjMuODYzMSwtNzQuNDMzOSAtMS41MDI2LC0xMy44NTQgLTAuODA2OCwtMjguODM0NiAxLjQwMjUsLTMwLjIwMDEgMC41ODYzLC0wLjM2MjMgNC41OTQyLDIuNDI5NCA4LjkwNjcsNi4yMDM3IDIwLjUzOTMsMTcuOTc1OCA0Ny4zMjgsMzUuODcxMiA2OS44NDEsNDYuNjU1MSAzMS41MjY4LDE1LjEwMTcgNTEuNTAwNywyMS43NTg2IDEwMy4zMzM0LDM0LjQzOTMgNDMuNjUzMiwxMC42Nzk2IDU4Ljg2NDcsMTUuNjkyMSA4My4xNjAxLDI3LjQwMjggMjMuNjMzMywxMS4zOTE0IDUwLjgzOTksMjguMzIyIDUwLjgzOTksMzEuNjM3NCAwLDEuNDggLTcwLjE2MzcsMzUuNzk3NiAtOTQuMjY5Niw0Ni4xMDgxIC0yMS4zODEsOS4xNDQ5IC00Mi4yNDAzLDE1Ljk0MjUgLTUxLjczMDQsMTYuODU3OCAtNC45NzM5LDAuNDc5NyAtOS43MTM4LC0wLjMyMTIgLTE4LjY2NjcsLTMuMTUzOSB6IiBpZD0icGF0aDQyMC01LTQiIC8+CiAgICAgICAgPHBhdGggc3R5bGU9ImZpbGw6I2ZmZmZmZjtmaWxsLW9wYWNpdHk6MTtzdHJva2Utd2lkdGg6Mzg3Ljc3O3N0cm9rZS1kYXNoYXJyYXk6bm9uZSIgZD0ibSAyMDE3LjEwNzMsMjQwMy44NjU3IGMgLTY2LjE2NjYsLTEyLjU1NjIgLTEyOS42OTUzLC00NC4zMjcyIC0yMDAuOTg2NCwtMTAwLjUxNDEgbCAtMTIsLTkuNDU3NiAtOS4zMzMzLC0wLjAyIGMgLTEyLjU4MDMsLTAuMDI4IC0zNy43MDgzLDQuMjI3NCAtNTgsOS44MjE1IC0yNi4zNzc0LDcuMjcxOCAtNTQuMzM4MSwxOC4zMjU1IC0xMDAuNjY2NywzOS43OTY2IC0yOS42NDY1LDEzLjczOTggLTQ5LjU2NzIsMjIuMzYwOCAtNTEuNjY5MiwyMi4zNjA4IC00LjQ1ODUsMCAtNjguOTk3NSwtNjkuOTI0MSAtNjguOTk3NSwtNzQuNzU0NyAwLC0wLjUxMDkgNS4yNSwtMy4xNzMzIDExLjY2NjcsLTUuOTE2NiA2LjQxNjcsLTIuNzQzMiAzMy44NjY3LC0xNS42NDcxIDYxLC0yOC42NzU0IDc5LjA3MDksLTM3Ljk2NjUgMTAxLjc0OTcsLTQ3LjE3NzYgMTM5LjMzMzMsLTU2LjU5MDggMzEuNDAzOCwtNy44NjU0IDQxLjk1NDIsLTkuMjMzIDcxLjMzMzQsLTkuMjQ2NSAzNS4zMDE1LC0wLjAxNiA1OS41Mzg3LDQuMjUxMiA5MS4xNTIzLDE2LjA0OTEgNzMuNjQ3OSwyNy40ODQ2IDEzMy41MjY5LDkyLjQzMDggMTQ0Ljc5NTMsMTU3LjA0ODUgMi44MDk0LDE2LjExMDIgMi41MTkyLDQzLjcwMzMgLTAuNDU1NCw0My4zMTA4IC0wLjQ1NDEsLTAuMDYgLTguMTgxNywtMS41MDQ5IC0xNy4xNzI1LC0zLjIxMTEgeiIgaWQ9InBhdGg0MTgtMy03NCIgLz4KICAgICAgICA8cGF0aCBzdHlsZT0iZmlsbDojZmZmZmZmO2ZpbGwtb3BhY2l0eToxO3N0cm9rZS13aWR0aDozODcuNzc7c3Ryb2tlLWRhc2hhcnJheTpub25lIiBkPSJtIDE1MTguNzg3NiwyNDQ1Ljc4NTQgYyAtMzUuNDYsLTMuNDQ3MyAtNzAuMjA1LC0xNS44MDk0IC05OS43ODk1LC0zNS41MDQ3IC0xNS45MjY2LC0xMC42MDI4IC0zOS4yMzQyLC0zMi42OTk1IC01MC45MzI3LC00OC4yODY5IC0yMS42NjAzLC0yOC44NjA3IC0zNi42NDQyLC02Ni4wODY0IC0zOC44MzI1LC05Ni40NzQ4IC0wLjczMDQsLTEwLjE0MzUgLTAuNTYyNCwtMTEuNjY2NiAxLjI4NzUsLTExLjY2NjYgMS4xNzAyLDAgOC4wMDksMy43MDkzIDE1LjE5NzMsOC4yNDMgMzguOTk4NywyNC41OTYzIDgwLjY2NTEsMzcuNzU2NSAxMjQuNzEwNiwzOS4zODk1IGwgMTkuNjQwOSwwLjcyODEgNy40NjA4LDkuOTEyNiBjIDMxLjQ0NzYsNDEuNzgyIDc2LjE0NDgsODQuOTY4NSAxMTkuODQ5MiwxMTUuNzk4NSBsIDkuMjU4NCw2LjUzMTEgLTcuOTI1MSwyLjQxMzMgYyAtMjYuMDk0Myw3Ljk0NTkgLTY5Ljc5NzQsMTEuODQ1OCAtOTkuOTI0OSw4LjkxNjkgeiIgaWQ9InBhdGg0MTYtNS00IiAvPgogICAgICAgIDxwYXRoIHN0eWxlPSJmaWxsOiNmZmZmZmY7ZmlsbC1vcGFjaXR5OjE7c3Ryb2tlLXdpZHRoOjM4Ny43NztzdHJva2UtZGFzaGFycmF5Om5vbmUiIGQ9Im0gMTkwMS40NTQyLDI1MTguMzQzNCBjIC05NS4yMjE0LC0xMC4zMjI5IC0xOTYuNzg5MywtNTQuNzcyMyAtMjgzLjgwODQsLTEyNC4yMDM1IGwgLTkuMTY0OCwtNy4zMTI0IDIxLjgyLC0xMC42MjM4IGMgNDkuNTY0OCwtMjQuMTMyNCA2My45MDY3LC0zMC45MDEyIDc4LjY4MDMsLTM3LjEzNCA4LjUzOTksLTMuNjAyOSAxNS44NzcyLC02LjU1MDcgMTYuMzA1LC02LjU1MDcgMC40Mjc5LDAgNC44NDA3LDIuOTUyNiA5LjgwNjMsNi41NjEyIDIxLjExNjksMTUuMzQ2NCA1OC4yODY1LDM1LjY0NzQgODYuNDY4NCw0Ny4yMjY3IDYwLjQ3MTksMjQuODQ2NSAxNDAuMjIyLDQyLjIxMjEgMTkzLjg1NTMsNDIuMjEyMSA3LjM1NDIsMCAxMy4zNzEzLDAuMzYxNiAxMy4zNzEzLDAuODAzNiAwLDAuNDQxOSAtMi4zMzUyLDUuNzg2NyAtNS4xODkzLDExLjg3NzIgLTEyLjc0NTIsMjcuMTk3NSAtMzQuMDYwMiw1My4yNDgyIC01OS43MzAyLDczLjAwMDggbCAtOC4yMTEzLDYuMzE4NCAtMTguNDM0NiwtMC4xNDgyIGMgLTEwLjEzOTEsLTAuMDgyIC0yNi4yMzQ2LC0wLjk5MzkgLTM1Ljc2OCwtMi4wMjc0IHoiIGlkPSJwYXRoNDE0LTYtMyIgLz4KICAgICAgICA8cGF0aCBzdHlsZT0iZmlsbDojZmZmZmZmO2ZpbGwtb3BhY2l0eToxO3N0cm9rZS13aWR0aDozODcuNzc7c3Ryb2tlLWRhc2hhcnJheTpub25lIiBkPSJtIDE3MjguNzg3NiwyNTgwLjk1NDggYyAtNzMuMTczMywtMy4yNDA1IC0xMzcuOTYxMywtMjYuOTYyOSAtMTg0LC02Ny4zNzIyIC0xMy45Njk5LC0xMi4yNjE3IC0zMC42NjY4LC0zMS43MDQxIC0zMC42NjY4LC0zNS43MDk1IDAsLTAuNTE3MyA5Ljk5NjYsLTEuMzUwMyAyMi4yMTQ3LC0xLjg1MTEgMzYuMTI2MywtMS40ODA3IDcxLjMxOTIsLTYuOTE3OSAxMDQuMzkzOSwtMTYuMTI4NyBsIDE2LjYwODYsLTQuNjI1MiAxMi4wNTgyLDcuNzM0MiBjIDE5LjYwOTcsMTIuNTc3OCAyNy40NDE4LDE3LjA0MDcgNDYuOTE4NiwyNi43MzQ4IDU3Ljc4MzMsMjguNzYwNiAxMTcuNDU3MSw0Ni42Njg5IDE3NC4yOTY4LDUyLjMwNzIgOS4yNjU1LDAuOTE5MSAxNi4zNjIxLDIuMTU1MyAxNS43NzAyLDIuNzQ3MSAtMS44MzI5LDEuODMyOCAtMjUuOTEwOSwxMS4yODU0IC00My4xNjA5LDE2Ljk0NDEgLTMyLjA3MzgsMTAuNTIxNiAtNjMuMTc5OSwxNi40ODI0IC05Ny43NDM5LDE4LjczMDcgLTExLjcyMDgsMC43NjI0IC0yMi44MjA4LDEuMjcwNiAtMjQuNjY2NywxLjEyOTMgLTEuODQ1OCwtMC4xNDEzIC03LjI1NjEsLTAuNDI5NiAtMTIuMDIyNywtMC42NDA3IHoiIGlkPSJwYXRoNDEyLTItMDciIC8+CiAgICAgIDwvZz4KICAgIDwvZz4KICA8L2c+Cjwvc3ZnPgo=";

},
"standalone/src/document-draft.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.DRAFT_KEY = void 0;
exports.encodeDraftAsset = encodeDraftAsset;
exports.restoreDraftAssets = restoreDraftAssets;
exports.readDocumentDraft = readDocumentDraft;
exports.DRAFT_KEY = 'ddn.designer.draft.v1';
function encodeDraftAsset(id, mime, bytes) {
    let binary = '';
    for (let index = 0; index < bytes.length; index += 8192)
        binary += String.fromCharCode(...bytes.subarray(index, index + 8192));
    return { id, mime, base64: btoa(binary) };
}
function restoreDraftAssets(draft) {
    return new Map(draft.assets.map(asset => {
        const binary = atob(asset.base64), bytes = Uint8Array.from(binary, char => char.charCodeAt(0));
        return [asset.id, new File([bytes], asset.id, { type: asset.mime })];
    }));
}
function readDocumentDraft(text) {
    try {
        const value = JSON.parse(text ?? 'null');
        if (!value || typeof value !== 'object' || !('entry' in value) || typeof value.entry !== 'string' || !('files' in value) || !Array.isArray(value.files))
            return;
        const files = [], seen = new Set();
        for (const item of value.files) {
            if (!item || typeof item !== 'object' || !('id' in item) || typeof item.id !== 'string' || seen.has(item.id) || !('text' in item) || typeof item.text !== 'string')
                return;
            seen.add(item.id);
            files.push({ id: item.id, text: item.text, revision: 'recovered', encoding: 'utf-8', writable: !('writable' in item) || item.writable !== false });
        }
        if (!seen.has(value.entry))
            return;
        const assets = [];
        if ('assets' in value) {
            if (!Array.isArray(value.assets))
                return;
            for (const item of value.assets) {
                if (!item || typeof item !== 'object' || !('id' in item) || typeof item.id !== 'string' || !('mime' in item) || typeof item.mime !== 'string' || !('base64' in item) || typeof item.base64 !== 'string')
                    return;
                atob(item.base64);
                assets.push({ id: item.id, mime: item.mime, base64: item.base64 });
            }
        }
        return { version: 1, entry: value.entry, files, assets, savedAt: 'savedAt' in value && typeof value.savedAt === 'string' ? value.savedAt : '' };
    }
    catch {
        return;
    }
}

},
"standalone/src/menus.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.openPopupMenu = openPopupMenu;
exports.createMenuBar = createMenuBar;
const enabledOf = (item) => {
    try {
        return item.enabled ? item.enabled() : true;
    }
    catch {
        return false;
    }
};
function openPopupMenu(anchor, items, label, onError) {
    const document = anchor.ownerDocument, view = document.defaultView;
    document.querySelector('.app-popup-menu')?.remove();
    const menu = document.createElement('div');
    menu.className = 'app-menu app-popup-menu';
    menu.setAttribute('role', 'menu');
    menu.setAttribute('aria-label', label);
    menu.style.position = 'fixed';
    const close = (focus = true) => {
        menu.remove();
        document.removeEventListener('pointerdown', outside, true);
        anchor.setAttribute('aria-expanded', 'false');
        if (focus)
            anchor.focus();
    };
    const outside = (event) => {
        if (!(event.target instanceof Node) || !menu.contains(event.target) && event.target !== anchor)
            close(false);
    };
    for (const item of items) {
        if (item.kind === 'separator') {
            const rule = document.createElement('hr');
            rule.setAttribute('role', 'separator');
            menu.append(rule);
            continue;
        }
        if (item.kind === 'heading' || item.kind === 'submenu')
            continue;
        const button = document.createElement('button');
        button.type = 'button';
        button.tabIndex = -1;
        const checked = item.checked?.();
        button.setAttribute('role', checked === undefined ? 'menuitem' : 'menuitemradio');
        if (checked !== undefined)
            button.setAttribute('aria-checked', String(checked));
        button.setAttribute('aria-label', item.label);
        const mark = document.createElement('span');
        mark.className = 'app-menu-check';
        mark.textContent = checked ? '•' : '';
        const text = document.createElement('span');
        text.className = 'app-menu-label';
        text.textContent = item.label;
        button.append(mark, text);
        if (item.shortcut) {
            const kbd = document.createElement('kbd');
            kbd.textContent = item.shortcut;
            button.append(kbd);
        }
        if (!enabledOf(item))
            button.setAttribute('aria-disabled', 'true');
        button.addEventListener('click', () => {
            if (button.getAttribute('aria-disabled') === 'true')
                return;
            close();
            if (item.run)
                Promise.resolve().then(item.run).catch(onError);
        });
        menu.append(button);
    }
    menu.addEventListener('keydown', event => {
        const buttons = [...menu.querySelectorAll('button')], index = buttons.indexOf(document.activeElement);
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            buttons[(index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length]?.focus();
        }
        else if (event.key === 'Escape' || event.key === 'Tab') {
            event.preventDefault();
            close();
        }
    });
    document.body.append(menu);
    const a = anchor.getBoundingClientRect(), m = menu.getBoundingClientRect();
    menu.style.left = Math.max(4, Math.min(a.right - m.width, view.innerWidth - m.width - 4)) + 'px';
    menu.style.top = (a.top - m.height - 4 >= 4 ? a.top - m.height - 4 : Math.min(a.bottom + 4, view.innerHeight - m.height - 4)) + 'px';
    anchor.setAttribute('aria-expanded', 'true');
    document.addEventListener('pointerdown', outside, true);
    (menu.querySelector('[aria-checked=true]') ?? menu.querySelector('button'))?.focus();
}
function createMenuBar(document, specs, options) {
    const bar = document.createElement('div');
    bar.className = 'app-menubar';
    bar.setAttribute('role', 'menubar');
    bar.setAttribute('aria-label', options.label);
    const tops = [];
    let openIndex = -1;
    const closeSubmenus = (panel) => {
        for (const sub of panel.querySelectorAll('.app-submenu'))
            sub.hidden = true;
        for (const trigger of panel.querySelectorAll('[aria-haspopup=menu]'))
            trigger.setAttribute('aria-expanded', 'false');
    };
    function close(focusTop = false) {
        if (openIndex < 0)
            return;
        const top = tops[openIndex];
        top.panel.hidden = true;
        closeSubmenus(top.panel);
        top.button.setAttribute('aria-expanded', 'false');
        if (focusTop)
            top.button.focus();
        openIndex = -1;
        bar.removeAttribute('data-open');
    }
    const itemsOf = (panel) => [...panel.children].flatMap(child => child.matches('[role^=menuitem]') ? [child] : child.classList.contains('app-submenu-host') ? [child.firstElementChild] : []);
    function run(action) {
        close();
        if (action)
            Promise.resolve().then(action).catch(options.onError);
    }
    function render(panel, items) {
        panel.replaceChildren();
        for (const item of items) {
            if (item.kind === 'separator') {
                const rule = document.createElement('hr');
                rule.setAttribute('role', 'separator');
                panel.append(rule);
                continue;
            }
            if (item.kind === 'heading') {
                const head = document.createElement('div');
                head.className = 'app-menu-head';
                head.setAttribute('role', 'presentation');
                head.textContent = item.label;
                panel.append(head);
                continue;
            }
            const button = document.createElement('button');
            button.type = 'button';
            button.tabIndex = -1;
            button.setAttribute('aria-label', item.label);
            const enabled = enabledOf(item);
            if (!enabled) {
                button.setAttribute('aria-disabled', 'true');
                if (item.hint)
                    button.title = item.hint;
            }
            const mark = document.createElement('span');
            mark.className = 'app-menu-check';
            mark.setAttribute('aria-hidden', 'true');
            const text = document.createElement('span');
            text.className = 'app-menu-label';
            text.textContent = item.label;
            button.append(mark, text);
            if (item.kind === 'submenu') {
                button.setAttribute('role', 'menuitem');
                button.setAttribute('aria-haspopup', 'menu');
                button.setAttribute('aria-expanded', 'false');
                const arrow = document.createElement('span');
                arrow.className = 'app-menu-arrow';
                arrow.setAttribute('aria-hidden', 'true');
                arrow.textContent = '›';
                button.append(arrow);
                const host = document.createElement('div');
                host.className = 'app-submenu-host';
                const sub = document.createElement('div');
                sub.className = 'app-menu app-submenu';
                sub.setAttribute('role', 'menu');
                sub.setAttribute('aria-label', item.label);
                sub.hidden = true;
                host.append(button, sub);
                panel.append(host);
                const openSub = (focus) => {
                    if (!enabledOf(item))
                        return;
                    for (const other of panel.querySelectorAll(':scope > .app-submenu-host > .app-submenu'))
                        if (other !== sub) {
                            other.hidden = true;
                            other.previousElementSibling?.setAttribute('aria-expanded', 'false');
                        }
                    render(sub, item.items());
                    sub.hidden = false;
                    button.setAttribute('aria-expanded', 'true');
                    sub.removeAttribute('data-flip');
                    const bounds = sub.getBoundingClientRect(), view = document.defaultView;
                    if (bounds.right > view.innerWidth - 4)
                        sub.dataset.flip = '';
                    if (focus)
                        itemsOf(sub)[0]?.focus();
                };
                button.addEventListener('click', () => openSub(true));
                button.addEventListener('pointerenter', () => openSub(false));
                button.addEventListener('keydown', event => {
                    if (event.key === 'ArrowRight' || event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        event.stopPropagation();
                        openSub(true);
                    }
                });
                continue;
            }
            const checked = item.checked?.();
            button.setAttribute('role', checked === undefined ? 'menuitem' : item.radio ? 'menuitemradio' : 'menuitemcheckbox');
            if (checked !== undefined) {
                button.setAttribute('aria-checked', String(checked));
                mark.textContent = checked ? (item.radio ? '•' : '✓') : '';
            }
            if (item.badge) {
                const badge = document.createElement('span');
                badge.className = 'app-menu-badge';
                badge.textContent = item.badge;
                button.append(badge);
            }
            if (item.shortcut) {
                const kbd = document.createElement('kbd');
                kbd.textContent = item.shortcut;
                button.append(kbd);
            }
            button.addEventListener('pointerenter', () => {
                for (const other of panel.querySelectorAll(':scope > .app-submenu-host > .app-submenu')) {
                    other.hidden = true;
                    other.previousElementSibling?.setAttribute('aria-expanded', 'false');
                }
            });
            button.addEventListener('click', () => {
                if (button.getAttribute('aria-disabled') !== 'true')
                    run(item.run);
            });
            panel.append(button);
        }
    }
    function open(index, focusFirst) {
        if (openIndex !== index)
            close();
        const top = tops[index];
        if (!top)
            return;
        openIndex = index;
        render(top.panel, top.spec.items());
        top.panel.hidden = false;
        top.button.setAttribute('aria-expanded', 'true');
        bar.dataset.open = '';
        top.panel.style.left = '';
        const bounds = top.panel.getBoundingClientRect(), width = document.defaultView.innerWidth;
        if (bounds.right > width - 4)
            top.panel.style.left = Math.max(-bounds.left + 4, width - 4 - bounds.right) + 'px';
        if (focusFirst)
            itemsOf(top.panel)[0]?.focus();
        else
            top.button.focus();
    }
    specs.forEach((spec, index) => {
        const host = document.createElement('div');
        host.className = 'app-menu-host';
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = spec.label;
        button.tabIndex = index === 0 ? 0 : -1;
        button.setAttribute('role', 'menuitem');
        button.setAttribute('aria-haspopup', 'menu');
        button.setAttribute('aria-expanded', 'false');
        const panel = document.createElement('div');
        panel.className = 'app-menu';
        panel.setAttribute('role', 'menu');
        panel.setAttribute('aria-label', spec.label);
        panel.hidden = true;
        host.append(button, panel);
        bar.append(host);
        tops.push({ button, panel, spec });
        button.addEventListener('click', () => {
            if (openIndex === index)
                close();
            else
                open(index, false);
        });
        button.addEventListener('pointerenter', () => {
            if (openIndex >= 0 && openIndex !== index)
                open(index, false);
        });
        button.addEventListener('focus', () => {
            for (const other of tops)
                other.button.tabIndex = other.button === button ? 0 : -1;
        });
        button.addEventListener('keydown', event => {
            const move = (step) => {
                const next = (index + step + tops.length) % tops.length;
                if (openIndex >= 0)
                    open(next, true);
                else
                    tops[next].button.focus();
            };
            if (event.key === 'ArrowRight') {
                event.preventDefault();
                move(1);
            }
            else if (event.key === 'ArrowLeft') {
                event.preventDefault();
                move(-1);
            }
            else if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                open(index, true);
            }
            else if (event.key === 'ArrowUp') {
                event.preventDefault();
                open(index, false);
                const items = itemsOf(panel);
                items.at(-1)?.focus();
            }
            else if (event.key === 'Escape' && openIndex >= 0) {
                event.preventDefault();
                close(true);
            }
        });
        panel.addEventListener('keydown', event => {
            const current = event.target.closest('[role^=menuitem]');
            const container = current?.closest('.app-menu');
            if (!current || !container)
                return;
            const items = itemsOf(container), position = items.indexOf(current);
            const isSub = container.classList.contains('app-submenu');
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                event.stopPropagation();
                items[(position + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus();
            }
            else if (event.key === 'Home' || event.key === 'End') {
                event.preventDefault();
                items[event.key === 'Home' ? 0 : items.length - 1]?.focus();
            }
            else if (event.key === 'ArrowLeft') {
                event.preventDefault();
                event.stopPropagation();
                if (isSub) {
                    container.hidden = true;
                    const trigger = container.previousElementSibling;
                    trigger?.setAttribute('aria-expanded', 'false');
                    trigger?.focus();
                }
                else
                    open((index - 1 + tops.length) % tops.length, true);
            }
            else if (event.key === 'ArrowRight' && current.getAttribute('aria-haspopup') !== 'menu') {
                event.preventDefault();
                event.stopPropagation();
                open((index + 1) % tops.length, true);
            }
            else if (event.key === 'Escape') {
                event.preventDefault();
                event.stopPropagation();
                if (isSub) {
                    container.hidden = true;
                    const trigger = container.previousElementSibling;
                    trigger?.setAttribute('aria-expanded', 'false');
                    trigger?.focus();
                }
                else
                    close(true);
            }
            else if (event.key === 'Tab')
                close();
            else if (event.key.length === 1 && /\S/.test(event.key) && !event.ctrlKey && !event.metaKey && !event.altKey) {
                const letter = event.key.toLowerCase(), order = [...items.slice(position + 1), ...items.slice(0, position + 1)];
                order.find(item => (item.getAttribute('aria-label') ?? '').toLowerCase().startsWith(letter))?.focus();
            }
        });
    });
    document.addEventListener('pointerdown', event => {
        if (openIndex >= 0 && !(event.target instanceof Node && bar.contains(event.target)))
            close();
    });
    return {
        element: bar, close: () => close(), isOpen: () => openIndex >= 0,
        refresh() {
            if (openIndex < 0)
                return;
            const top = tops[openIndex];
            if (top.panel.querySelector('.app-submenu:not([hidden])'))
                return;
            const focused = itemsOf(top.panel).indexOf(document.activeElement);
            render(top.panel, top.spec.items());
            if (focused >= 0)
                itemsOf(top.panel)[focused]?.focus();
        },
    };
}

},
"standalone/src/modular-shell.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.bootModularShell = bootModularShell;
const shell_js_1 = require("standalone/src/shell.js");
const modular_loading_js_1 = require("standalone/src/modular-loading.js");
const website_navigation_js_1 = require("standalone/src/website-navigation.js");
function bootModularShell(factories, api) {
    (0, modular_loading_js_1.installModularWorkerFactory)();
    void (async () => {
        const initial = globalThis.DDN_SITE_INITIAL;
        if (initial)
            await (0, modular_loading_js_1.ensureProfileInput)(initial.sources, factories.mode !== 'verifier');
        Object.defineProperty(globalThis, 'DDN', { configurable: true, value: Object.freeze(api) });
        (0, shell_js_1.mountShell)({ ...factories, edition: 'complete',
            ...(initial ? { initial: { ...initial, view: new URLSearchParams(location.search).get('view') ?? undefined } } : {}),
            ready: state => {
                Object.defineProperty(globalThis, 'DDN_SITE_STATE', { configurable: true, value: state });
                document.documentElement.dataset.ready = 'true';
                factories.ready?.(state);
            },
        });
        if (initial || 'DDN_WEBSITE_CATALOGUE' in globalThis)
            (0, website_navigation_js_1.installWebsiteNavigation)(factories.mode);
    })().catch(error => {
        const status = document.createElement('p');
        status.setAttribute('role', 'alert');
        status.textContent = error instanceof Error ? error.message : String(error);
        document.body.append(status);
    });
}

},
"standalone/src/shell.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.mountShell = mountShell;
const drawer_js_1 = require("viewer/src/drawer.js");
const brand_js_1 = require("standalone/src/brand.js");
const ui_icons_js_1 = require("viewer/src/ui-icons.js");
const index_js_1 = require("model/src/index.js");
const ui_theme_js_1 = require("viewer/src/ui-theme.js");
const dialogs_js_1 = require("viewer/src/dialogs.js");
const choice_field_js_1 = require("viewer/src/choice-field.js");
const document_draft_js_1 = require("standalone/src/document-draft.js");
const index_js_2 = require("language/src/index.js");
const ui_commands_js_1 = require("viewer/src/ui-commands.js");
const popout_js_1 = require("viewer/src/popout.js");
const menus_js_1 = require("standalone/src/menus.js");
const zip_js_1 = require("standalone/src/zip.js");
const BLANK_DOCUMENT = '';
const examples = {
    'ERD whiteboard': 'erd Sales : Sales design\n    Customer\n    Order\n    connect Customer to Order\n',
    'Mind map': 'mindmap Product\n    Research\n        Interviews\n        Prototypes\n    Delivery\n        Design\n        Build\n',
    'Concept map': 'view Knowledge as "concept.map@1"\n    element Concept as object\n    element Evidence as object\n    connect Concept to Evidence as assoc : supports\n',
    'Table': 'data Tasks\n    task:lt:60.owner:lt.status:ct\n    Design.Alex.Draft\n    Build.Sam.In-progress\nview Records as table.records@1\n    with\n        projection.options\n            records Tasks\n            columns 3\n            missing gap\n',
};
function mountShell(factories) {
    const doc = document;
    const host = doc.defaultView;
    (0, ui_theme_js_1.installUITheme)(doc.body);
    let interfaceTheme = 'dark', interfaceTokens = {};
    (0, ui_theme_js_1.setUITheme)(doc.body, interfaceTheme);
    try {
        const saved = JSON.parse(localStorage.getItem('ddn.interface.v1') ?? 'null');
        if (saved) {
            (0, ui_theme_js_1.setUITheme)(doc.body, saved.name, saved.overrides);
            interfaceTheme = saved.name;
            interfaceTokens = saved.overrides ?? {};
        }
    }
    catch { }
    const query = new URLSearchParams(doc.defaultView?.location.search);
    const requestedTheme = query.get('theme');
    if (ui_theme_js_1.UI_THEME_NAMES.includes(requestedTheme)) {
        interfaceTheme = requestedTheme;
        interfaceTokens = {};
        (0, ui_theme_js_1.setUITheme)(doc.body, interfaceTheme);
    }
    const isDesigner = factories.mode === 'designer', isVerifier = factories.mode === 'verifier';
    doc.title = 'DDN ' + (isDesigner ? 'Designer' : isVerifier ? 'Verifier' : 'Viewer');
    const style = doc.createElement('style');
    style.textContent = `
:root{font-family:Inter,system-ui,sans-serif;color:var(--ddn-ui-text);background:var(--ddn-ui-bg)}
*{box-sizing:border-box}body{margin:0;min-height:100vh;height:100dvh;display:flex;flex-direction:column;background:var(--ddn-ui-bg);color:var(--ddn-ui-text);font-size:var(--ddn-ui-font-size)}
button,select,input,textarea{font:inherit}button{display:inline-flex;align-items:center;justify-content:center;gap:7px;cursor:pointer;border:1px solid var(--ddn-ui-border);background:var(--ddn-ui-surface);border-radius:9px;padding:6px 10px;color:var(--ddn-ui-text);transition:background .15s,border-color .15s,box-shadow .15s}
button:hover{background:color-mix(in srgb,var(--ddn-ui-accent) 9%,var(--ddn-ui-surface));border-color:color-mix(in srgb,var(--ddn-ui-accent) 55%,var(--ddn-ui-border))}button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,a:focus-visible{outline:2px solid var(--ddn-ui-accent);outline-offset:3px}
button>svg,.app-source-heading>svg{width:16px;height:16px;flex:none}select,input{color:var(--ddn-ui-text);background:var(--ddn-ui-input);border:1px solid var(--ddn-ui-border);border-radius:8px;padding:5px 8px;min-height:30px}select{max-width:100%;text-overflow:ellipsis}button:disabled{cursor:default;opacity:.55}
.app-bar{display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:6px 14px;min-height:48px;background:color-mix(in srgb,var(--ddn-ui-surface) 88%,transparent);border-bottom:1px solid var(--ddn-ui-border);backdrop-filter:blur(16px);flex:none}
.app-brand{display:flex;align-items:center;gap:10px;min-width:0}.app-brand-mark{display:grid;place-items:center;width:32px;height:32px;flex:none;border:1px solid color-mix(in srgb,var(--ddn-ui-accent) 25%,var(--ddn-ui-border));border-radius:9px;background:color-mix(in srgb,var(--ddn-ui-accent) 7%,var(--ddn-ui-bg))}.app-brand-mark img{width:22px;height:22px;object-fit:contain}.app-brand-mark .app-logo-dark{display:none}[data-ddn-ui-theme=dark] .app-brand-mark .app-logo-light,[data-ddn-ui-theme=midnight] .app-brand-mark .app-logo-light{display:none}[data-ddn-ui-theme=dark] .app-brand-mark .app-logo-dark,[data-ddn-ui-theme=midnight] .app-brand-mark .app-logo-dark{display:block}
.app-brand-copy{display:flex;flex-direction:column;gap:1px;min-width:0}.app-bar strong{font-size:14px;letter-spacing:-.03em;font-weight:700;line-height:1.2;white-space:nowrap}.app-bar small{font-size:10px;color:var(--ddn-ui-muted);letter-spacing:.02em;white-space:nowrap}.app-interface{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-left:auto}.app-interface label{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--ddn-ui-muted)}.app-interface select{min-width:90px;min-height:30px;padding:4px 8px}.app-interface button{min-height:30px;padding:4px 9px;font-size:12px}
.app-site-links{display:flex;align-items:center;gap:2px;flex-wrap:wrap}.app-site-links a{display:inline-flex;align-items:center;gap:5px;padding:5px 8px;border-radius:7px;color:var(--ddn-ui-muted);text-decoration:none;font-size:12px}.app-site-links a:hover{background:color-mix(in srgb,var(--ddn-ui-accent) 10%,transparent);color:var(--ddn-ui-text)}.app-site-links a svg{width:14px;height:14px}.app-site-links a[aria-current=page]{color:var(--ddn-ui-accent);background:color-mix(in srgb,var(--ddn-ui-accent) 12%,transparent);font-weight:650}
.app-document-toggle{display:none}.app-tools{display:flex;gap:6px;align-items:center;flex-wrap:wrap;padding:5px 14px;border-bottom:1px solid var(--ddn-ui-border);background:color-mix(in srgb,var(--ddn-ui-surface) 65%,var(--ddn-ui-bg));flex:none}.app-tools button{min-height:30px;padding:5px 9px;font-size:12px;white-space:nowrap}.app-tools label{display:flex;align-items:center;gap:6px;min-width:0;max-width:100%;font-size:11px;color:var(--ddn-ui-muted)}.app-tools label[hidden],.app-tools button[hidden],.app-source-toolbar button[hidden]{display:none}.app-tools select{min-width:0;max-width:240px;font-size:12px;min-height:30px}.app-tools input:not([type=file]){max-width:120px}.app-tools .app-primary,.app-source-toolbar .app-primary{background:var(--ddn-ui-accent);color:var(--ddn-ui-accent-text);border-color:transparent;font-weight:650}.app-tools .app-primary:hover,.app-source-toolbar .app-primary:hover{filter:brightness(1.08)}.app-tools .app-spacer{flex:1 1 auto}
.app-menu-host{position:relative}.app-menu{position:absolute;top:calc(100% + 4px);left:0;z-index:60;min-width:230px;display:grid;gap:2px;padding:6px;background:var(--ddn-ui-surface);border:1px solid var(--ddn-ui-border);border-radius:10px;box-shadow:0 14px 40px color-mix(in srgb,var(--ddn-ui-shadow) 70%,transparent)}.app-menu[hidden]{display:none}.app-menu button{justify-content:flex-start;gap:9px;border:0;background:transparent;border-radius:7px;padding:7px 9px;font-size:12px;width:100%;text-align:left}.app-menu button:hover,.app-menu button:focus-visible{background:color-mix(in srgb,var(--ddn-ui-accent) 12%,var(--ddn-ui-surface));color:var(--ddn-ui-text)}.app-menu button kbd{margin-left:auto;font:11px ui-monospace,monospace;color:var(--ddn-ui-muted)}.app-menu hr{width:100%;border:0;border-top:1px solid var(--ddn-ui-border);margin:3px 0}.app-menu .app-menu-head{padding:4px 9px 2px;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--ddn-ui-muted)}
.app-main{display:grid;grid-template-columns:minmax(230px,24%) minmax(0,1fr);flex:1;min-height:360px;gap:10px;padding:10px 12px;isolation:isolate;position:relative}.app-source{display:flex;flex-direction:column;min-height:0;min-width:0;border:1px solid var(--ddn-ui-border);border-radius:12px;background:var(--ddn-ui-surface);overflow:hidden;box-shadow:0 6px 24px color-mix(in srgb,var(--ddn-ui-shadow) 45%,transparent)}.app-source-heading{display:flex;align-items:center;gap:8px;padding:8px 10px;border-bottom:1px solid var(--ddn-ui-border);font-size:12px;font-weight:650}.app-source-heading>svg{color:var(--ddn-ui-accent)}.app-source-kind{margin-left:auto;font-size:10px;font-weight:500;color:var(--ddn-ui-muted);text-transform:uppercase;letter-spacing:.07em}
.app-source-toolbar{display:flex;align-items:center;gap:5px;flex-wrap:wrap;padding:6px 8px;border-bottom:1px solid var(--ddn-ui-border);background:color-mix(in srgb,var(--ddn-ui-surface) 65%,var(--ddn-ui-bg))}.app-source-toolbar button{min-height:28px;padding:3px 9px;font-size:12px}.app-source-toolbar .app-dirty{margin-left:auto;font-size:11px;color:var(--ddn-ui-muted)}.app-source-toolbar .app-dirty[data-state=dirty]{color:var(--ddn-ui-accent);font-weight:600}
.app-source textarea{width:100%;resize:none;flex:1;min-height:140px;border:0;outline-offset:-3px;padding:12px 14px;background:var(--ddn-ui-input);color:var(--ddn-ui-text);font:12px/1.6 'JetBrains Mono',ui-monospace,monospace;tab-size:4;border-radius:0;scrollbar-color:var(--ddn-ui-border) transparent;white-space:pre;overflow:auto}.app-source textarea[aria-invalid=true]{box-shadow:inset 3px 0 0 var(--ddn-ui-danger)}
.app-diagnostics{max-height:112px;overflow:auto;border-top:1px solid var(--ddn-ui-border);font-size:11px;line-height:1.45;background:color-mix(in srgb,var(--ddn-ui-danger) 7%,var(--ddn-ui-surface))}.app-diagnostics:empty{display:none}.app-diagnostics button{display:flex;gap:8px;width:100%;text-align:left;border:0;border-radius:0;background:transparent;padding:6px 10px;color:var(--ddn-ui-text);font-size:11px;line-height:1.45;justify-content:flex-start}.app-diagnostics button:hover{background:color-mix(in srgb,var(--ddn-ui-danger) 14%,var(--ddn-ui-surface))}.app-diagnostics b{flex:none;color:var(--ddn-ui-danger);font-weight:650}
.app-note{padding:7px 12px;font-size:11px;line-height:1.5;color:var(--ddn-ui-muted);border-top:1px solid var(--ddn-ui-border)}.app-note kbd{font:10px ui-monospace,monospace;padding:1px 4px;border:1px solid var(--ddn-ui-border);border-radius:4px}
.app-surface{min-width:0;min-height:0;background:var(--ddn-ui-surface);border:1px solid var(--ddn-ui-border);border-radius:12px;overflow:hidden;box-shadow:0 6px 24px color-mix(in srgb,var(--ddn-ui-shadow) 45%,transparent)}.app-surface>.ddn-viewer{height:100%;min-height:0;border:0}.app-main[data-source-hidden=true]{grid-template-columns:minmax(0,1fr)}.app-main[data-source-hidden=true]>.app-source{display:none}
.app-banner{grid-column:1/-1;display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:8px 12px;border:1px solid color-mix(in srgb,var(--ddn-ui-accent) 40%,var(--ddn-ui-border));border-radius:10px;background:color-mix(in srgb,var(--ddn-ui-accent) 9%,var(--ddn-ui-surface));font-size:12px}.app-banner button{min-height:28px;padding:3px 9px;font-size:12px}.app-banner .app-primary{background:var(--ddn-ui-accent);color:var(--ddn-ui-accent-text);border-color:transparent;font-weight:650}.app-banner .app-spacer{flex:1 1 auto}
.app-status{padding:6px 14px;font-size:11px;line-height:1.5;color:var(--ddn-ui-muted);border-top:1px solid var(--ddn-ui-border);background:var(--ddn-ui-surface);flex:none;display:flex;gap:16px;align-items:center}.app-status:empty{display:none}.app-status .app-status-text{flex:1 1 auto;min-width:0}.app-status .app-saved{flex:none;color:var(--ddn-ui-muted)}.app-error .app-status-text{color:var(--ddn-ui-danger)}.app-report{padding:24px;overflow:auto;height:100%}.app-report h2{font-size:20px;letter-spacing:-.03em;margin:0 0 10px}.app-report>p{color:var(--ddn-ui-muted);font-size:12px}.app-report>input{width:min(100%,420px);margin:8px 0 18px}.app-report table{width:100%;border-collapse:collapse;text-align:left;font-size:12px}.app-report th,.app-report td{padding:12px 10px;border-bottom:1px solid var(--ddn-ui-border);vertical-align:top;overflow-wrap:anywhere}.app-report th{background:var(--ddn-ui-bg)}.app-report code{white-space:pre-wrap}.app-pending{font-weight:600;color:var(--ddn-ui-accent)}
.app-toasts{position:fixed;right:16px;bottom:48px;z-index:80;display:grid;gap:6px;pointer-events:none}.app-toast{pointer-events:auto;display:flex;align-items:center;gap:8px;padding:8px 12px;border-radius:10px;background:var(--ddn-ui-text);color:var(--ddn-ui-bg);font-size:12px;box-shadow:0 10px 30px color-mix(in srgb,var(--ddn-ui-shadow) 60%,transparent);animation:app-toast-in .18s ease-out}.app-toast[data-kind=error]{background:var(--ddn-ui-danger);color:#fff}.app-toast svg{width:14px;height:14px;flex:none}@keyframes app-toast-in{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.app-samples{display:grid;gap:4px;max-height:360px;overflow:auto;border:1px solid var(--ddn-ui-border);border-radius:8px;padding:4px}.app-samples button{justify-content:flex-start;text-align:left;border:0;background:transparent;border-radius:6px;padding:6px 8px;gap:8px;width:100%}.app-samples button[aria-pressed=true]{background:color-mix(in srgb,var(--ddn-ui-accent) 15%,var(--ddn-ui-surface));color:var(--ddn-ui-accent)}.app-samples small{color:var(--ddn-ui-muted);margin-left:auto;font-size:10px;white-space:nowrap}.app-samples .app-menu-head{padding:6px 8px 2px;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--ddn-ui-muted)}
.app-shortcuts{display:grid;grid-template-columns:auto 1fr;gap:4px 14px;font-size:12px;margin:0}.app-shortcuts dt{font:11px ui-monospace,monospace;color:var(--ddn-ui-accent);white-space:nowrap}.app-shortcuts dd{margin:0}
@media(max-width:1050px){.app-bar{gap:10px;padding:6px 12px}.app-tools{padding:5px 12px}.app-main{padding:8px;gap:8px;grid-template-columns:minmax(210px,25%) minmax(0,1fr)}.app-tools select{max-width:200px}.app-bar small{display:none}}
@media(max-width:750px){.app-document-toggle{display:inline-flex}.app-tools:not([data-expanded=true]){display:none}body{height:auto;min-height:100dvh}.app-bar{padding:8px 10px;gap:8px}.app-brand{flex:1 1 auto}.app-interface{margin-left:0;gap:6px}.app-bar strong{font-size:13px}.app-interface label{font-size:11px}.app-tools{padding:8px 10px;gap:6px}.app-tools label{flex-wrap:wrap}.app-tools select{max-width:calc(100vw - 70px)}.app-main{grid-template-columns:minmax(0,1fr);flex:none;min-height:0;padding:8px;gap:8px}.app-source{height:280px}.app-surface{height:660px}.app-main[data-source-hidden=true] .app-surface{height:max(500px,calc(100dvh - 170px))}.app-status{padding:6px 10px}.app-report{padding:16px}.app-report td{padding:8px 5px}.app-toasts{right:8px;left:8px;bottom:40px}}
@media(max-width:760px){.app-surface:has(.ddn-viewer[data-ddn-dock-left]),.app-surface:has(.ddn-viewer[data-ddn-dock-right]){height:max(880px,calc(100dvh - 170px))}.app-surface:has(.ddn-viewer[data-ddn-dock-left][data-ddn-dock-right]){height:max(1100px,calc(100dvh - 170px))}}
@media(prefers-reduced-motion:reduce){button{transition:none}.app-toast{animation:none}}
.app-menubar{display:flex;align-items:center;gap:1px;min-width:0;flex:0 1 auto}.app-menubar>.app-menu-host>button{border:0;background:transparent;border-radius:7px;padding:5px 9px;min-height:30px;font-size:12.5px;font-weight:550;color:var(--ddn-ui-text)}.app-menubar>.app-menu-host>button:hover,.app-menubar>.app-menu-host>button[aria-expanded=true]{background:color-mix(in srgb,var(--ddn-ui-accent) 13%,transparent)}
.app-menu{max-height:calc(100dvh - 90px);overflow:auto;min-width:260px}.app-menu button{gap:6px}.app-menu button[aria-disabled=true]{opacity:.5;cursor:default}.app-menu button[aria-disabled=true]:hover{background:transparent}.app-menu .app-menu-check{width:14px;flex:none;text-align:center;color:var(--ddn-ui-accent);font-weight:700}.app-menu .app-menu-label{flex:1 1 auto;white-space:nowrap}.app-menu .app-menu-arrow{margin-left:auto;color:var(--ddn-ui-muted)}.app-menu .app-menu-badge{font-size:9.5px;letter-spacing:.04em;padding:1px 6px;border-radius:999px;border:1px solid var(--ddn-ui-border);color:var(--ddn-ui-muted);white-space:nowrap}.app-menu .app-menu-head{padding-left:29px}
.app-submenu-host{position:relative}.app-submenu{position:absolute;top:-6px;left:calc(100% + 2px);z-index:61}.app-submenu[data-flip]{left:auto;right:calc(100% + 2px)}
.app-bar .app-site-links:not(.app-mode-links) a span{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}.app-bar .app-site-links:not(.app-mode-links) a{padding:5px 6px}
.app-interface>label>.app-theme-word{display:none}
.app-main{grid-template-columns:var(--ddn-source-width,340px) 6px minmax(0,1fr);gap:0 4px}.app-main>.app-source{grid-column:1}.app-main>.app-splitter{grid-column:2}.app-main>.app-surface{grid-column:3}.app-main>.app-rail{display:none}
.app-splitter{cursor:col-resize;border-radius:4px;align-self:stretch;position:relative;outline-offset:-2px;touch-action:none}.app-splitter::after{content:'';position:absolute;inset:30% 2px;border-radius:2px;background:var(--ddn-ui-border);opacity:0;transition:opacity .15s}.app-splitter:hover::after,.app-splitter:focus-visible::after,.app-splitter[data-dragging]::after{opacity:1}
.app-rail{display:flex;flex-direction:column;align-items:center;gap:6px;padding:6px 0;border:1px solid var(--ddn-ui-border);border-radius:10px;background:var(--ddn-ui-surface)}.app-rail button{writing-mode:vertical-rl;transform:rotate(180deg);padding:10px 4px;min-height:0;font-size:11.5px;border:0;background:transparent;gap:6px}.app-rail button svg{transform:rotate(90deg)}
.app-source-heading .ddn-drawer-controls{display:flex;gap:2px;margin-left:auto}.app-source-heading .ddn-drawer-controls button{padding:4px;min-width:24px;width:24px;border:0;background:transparent;color:var(--ddn-ui-muted)}.app-source-heading .ddn-drawer-controls button[hidden]{display:none}.app-source-heading .app-source-collapse{margin-left:2px}
.app-main[data-source-hidden=true],.app-main[data-source-detached=true]{grid-template-columns:30px minmax(0,1fr)}.app-main[data-source-hidden=true]>.app-rail,.app-main[data-source-detached=true]>.app-rail{display:flex;grid-column:1}.app-main[data-source-hidden=true]>.app-surface,.app-main[data-source-detached=true]>.app-surface{grid-column:2}.app-main[data-source-hidden=true]>.app-splitter,.app-main[data-source-detached=true]>.app-splitter{display:none}.app-main[data-source-detached=true]>.app-source{display:none}
.app-source-heading .app-source-collapse{margin-left:4px;min-height:24px;padding:2px 6px;font-size:11px;border-color:transparent;background:transparent}.app-source-heading .app-source-collapse svg{width:13px;height:13px}
.app-zoom{display:flex;align-items:center;gap:2px;flex:none}.app-zoom[hidden]{display:none}.app-zoom button{min-height:22px;padding:1px 7px;font-size:11px;border-color:transparent;background:transparent}.app-zoom .app-zoom-value{min-width:62px;font-variant-numeric:tabular-nums;border-color:var(--ddn-ui-border)}
.app-bar{position:relative}.app-bar:has(.app-menubar[data-open]){z-index:55}.app-surface[data-ddn-menus] .ddn-viewer>.ddn-viewer-toolbar:not(.ddn-designer-toolbar),.app-surface[data-ddn-quick=hidden] .ddn-designer-toolbar{height:0;min-height:0;padding:0;margin:0;border:0;overflow:hidden;visibility:hidden}
.app-surface[data-ddn-outline=hidden] .ddn-viewer-outline{display:none}.app-surface[data-ddn-outline=hidden] .ddn-viewer:not([data-ddn-dock-left]){grid-template-columns:minmax(0,1fr)}.app-surface[data-ddn-outline=hidden] .ddn-viewer:not([data-ddn-dock-left]) .ddn-viewer-stage{grid-column:1}.app-surface[data-ddn-outline=hidden] .ddn-viewer:not([data-ddn-dock-left])[data-ddn-dock-right]{grid-template-columns:minmax(0,1fr) 320px}.app-surface[data-ddn-outline=hidden] .ddn-viewer:not([data-ddn-dock-left])[data-ddn-dock-right] .ddn-designer-dock-right{grid-column:2}
body[data-ddn-status=hidden] .app-status{display:none}
body[data-ddn-motion=reduced] *,body[data-ddn-motion=reduced] *::before,body[data-ddn-motion=reduced] *::after{transition:none!important;animation:none!important;scroll-behavior:auto!important}
body[data-ddn-contrast=high]{--ddn-ui-border:var(--ddn-ui-text);--ddn-ui-muted:var(--ddn-ui-text)}body[data-ddn-contrast=high] :focus-visible{outline-width:3px!important}
.app-command-list{display:grid;gap:2px;max-height:360px;overflow:auto;margin-top:8px}.app-command-list button{justify-content:flex-start;text-align:left;border:0;background:transparent;padding:6px 8px;gap:8px;width:100%}.app-command-list button[aria-selected=true]{background:color-mix(in srgb,var(--ddn-ui-accent) 15%,var(--ddn-ui-surface))}.app-command-list small{color:var(--ddn-ui-muted)}.app-command-list kbd{margin-left:auto;font:11px ui-monospace,monospace;color:var(--ddn-ui-muted)}
.app-tools[data-empty=true]{display:none}
@media(max-width:1050px){.app-bar .app-mode-links a span{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}}
@media(max-width:750px){.app-menubar{order:3;flex:1 1 100%;flex-wrap:wrap}.app-menubar>.app-menu-host>button{padding:4px 7px}.app-main,.app-main[data-source-hidden=true],.app-main[data-source-detached=true]{grid-template-columns:minmax(0,1fr)}.app-main>.app-source,.app-main>.app-surface,.app-main>.app-rail{grid-column:1!important}.app-main>.app-splitter{display:none}.app-rail{flex-direction:row;padding:0 6px}.app-rail button{writing-mode:horizontal-tb;transform:none}.app-rail button svg{transform:none}.app-tools[data-empty=true]{display:none!important}}`;
    doc.head.append(style);
    const bar = doc.createElement('header');
    bar.className = 'app-bar';
    const brandGroup = doc.createElement('div');
    brandGroup.className = 'app-brand';
    const mark = doc.createElement('span');
    mark.className = 'app-brand-mark';
    for (const [className, src] of [['app-logo-light', brand_js_1.ddnLogoDataURL], ['app-logo-dark', brand_js_1.ddnLogoDarkDataURL]]) {
        const logo = doc.createElement('img');
        logo.className = className;
        logo.src = src;
        logo.alt = 'DDN';
        logo.width = 22;
        logo.height = 22;
        mark.append(logo);
    }
    const brandCopy = doc.createElement('div');
    brandCopy.className = 'app-brand-copy';
    const brand = doc.createElement('strong');
    brand.textContent = doc.title;
    const sub = doc.createElement('small');
    sub.textContent = (factories.edition === 'complete' ? 'Complete profile edition' : 'Native edition') + ' · ddn-next-1 · everything runs locally';
    brandGroup.title = sub.textContent;
    brandCopy.append(brand, sub);
    brandGroup.append(mark, brandCopy);
    bar.append(brandGroup);
    const siteSlot = doc.createElement('div');
    siteSlot.className = 'app-site-slot';
    bar.append(siteSlot);
    const interfaceControls = doc.createElement('div');
    interfaceControls.className = 'app-interface';
    bar.append(interfaceControls);
    const tools = doc.createElement('nav');
    tools.className = 'app-tools';
    tools.setAttribute('aria-label', 'Document controls');
    const main = doc.createElement('main');
    main.className = 'app-main';
    const panel = doc.createElement('section');
    panel.className = 'app-source';
    panel.setAttribute('aria-label', 'DDN source');
    const sourceLabel = doc.createElement('label');
    sourceLabel.textContent = 'DDN source';
    const sourceHeading = doc.createElement('div');
    sourceHeading.className = 'app-source-heading';
    const sourceKind = doc.createElement('small');
    sourceKind.className = 'app-source-kind';
    sourceKind.textContent = factories.mode === 'viewer' ? 'Read only' : 'Source';
    sourceHeading.append((0, ui_icons_js_1.uiIcon)(doc, 'code'), sourceLabel, sourceKind);
    const sourceToolbar = doc.createElement('div');
    sourceToolbar.className = 'app-source-toolbar';
    sourceToolbar.setAttribute('role', 'toolbar');
    sourceToolbar.setAttribute('aria-label', 'Source actions');
    const editor = doc.createElement('textarea');
    editor.id = 'ddn-source';
    editor.setAttribute('aria-label', 'DDN source');
    editor.spellcheck = false;
    editor.readOnly = factories.mode === 'viewer';
    editor.wrap = 'off';
    sourceLabel.htmlFor = editor.id;
    const diagnosticsList = doc.createElement('div');
    diagnosticsList.className = 'app-diagnostics';
    diagnosticsList.setAttribute('role', 'list');
    diagnosticsList.setAttribute('aria-label', 'Source problems');
    const sourceNote = doc.createElement('div');
    sourceNote.className = 'app-note';
    sourceNote.append(doc.createTextNode(isDesigner ? 'Indent with spaces · ' : 'Indent with spaces. '));
    if (isDesigner) {
        const k1 = doc.createElement('kbd');
        k1.textContent = 'Ctrl+Enter';
        const k2 = doc.createElement('kbd');
        k2.textContent = 'Esc';
        const k3 = doc.createElement('kbd');
        k3.textContent = 'Tab';
        sourceNote.append(k1, doc.createTextNode(' applies · '), k2, doc.createTextNode(' then '), k3, doc.createTextNode(' leaves the editor. Nothing is uploaded; work is kept in this browser.'));
    }
    else
        sourceNote.append(doc.createTextNode('Nothing is uploaded; processing is local to this page.'));
    panel.append(sourceHeading, sourceToolbar, editor, diagnosticsList, sourceNote);
    const surface = doc.createElement('section');
    surface.className = 'app-surface';
    surface.setAttribute('aria-label', isVerifier ? 'Verification results' : 'Diagram workspace');
    main.append(panel, surface);
    const status = doc.createElement('footer');
    status.className = 'app-status';
    const statusText = doc.createElement('span');
    statusText.className = 'app-status-text';
    statusText.setAttribute('role', 'status');
    statusText.setAttribute('aria-live', 'polite');
    const savedIndicator = doc.createElement('span');
    savedIndicator.className = 'app-saved';
    status.append(statusText, savedIndicator);
    const toasts = doc.createElement('div');
    toasts.className = 'app-toasts';
    toasts.setAttribute('aria-live', 'polite');
    doc.body.replaceChildren(bar, tools, main, status, toasts);
    const files = new Map(), assets = new Map();
    let entry = 'main.ddn', sequence = 0, lastReport, viewer, designer, editorDirty = false, sourceConflict = false, editGeneration = 0, openGeneration = 0, pendingDocument = false;
    let cleanState = '', dirty = false, documentEntry = entry, replacing = false;
    let draftAssets = [], recoveryBanner;
    let lastOpened;
    let pendingRecovery = isDesigner && !factories.initial ? (0, document_draft_js_1.readDocumentDraft)(localStorageValue(document_draft_js_1.DRAFT_KEY)) : undefined;
    function localStorageValue(key) {
        try {
            return localStorage.getItem(key);
        }
        catch {
            return null;
        }
    }
    function workingSources() { return { entry: documentEntry, files: [...files.values()].map(file => file.id === entry && file.text !== editor.value ? { ...file, text: editor.value, originalBytes: new TextEncoder().encode(editor.value) } : file) }; }
    function contentState() { const source = workingSources(); return JSON.stringify([source.entry, source.files.map(file => [file.id, file.text]).sort((a, b) => String(a[0]).localeCompare(String(b[0])))]); }
    function markClean() { cleanState = contentState(); setDirty(false); }
    function clearRecovery() {
        pendingRecovery = undefined;
        recoveryBanner?.remove();
        recoveryBanner = undefined;
        clearTimeout(draftTimer);
        try {
            localStorage.removeItem(document_draft_js_1.DRAFT_KEY);
        }
        catch { }
        savedIndicator.textContent = '';
    }
    const setDirty = (value) => { dirty = isDesigner && value; doc.documentElement.dataset.ddnDirty = String(value); dirtyLabel.dataset.state = value ? 'dirty' : 'clean'; dirtyLabel.textContent = value ? 'Unsaved changes' : ''; };
    let cancellation;
    const verifier = isVerifier ? factories.verifier(factories.options()) : undefined;
    const toast = (text, kind = 'info') => {
        const item = doc.createElement('div');
        item.className = 'app-toast';
        item.dataset.kind = kind;
        item.append((0, ui_icons_js_1.uiIcon)(doc, kind === 'error' ? 'info' : 'check'), doc.createTextNode(text));
        toasts.append(item);
        while (toasts.children.length > 4)
            toasts.firstElementChild?.remove();
        setTimeout(() => { item.remove(); }, kind === 'error' ? 7000 : 3800);
    };
    const showError = (error) => { status.classList.add('app-error'); statusText.textContent = error instanceof Error ? error.message : String(error); toast(statusText.textContent, 'error'); };
    const notify = (text) => { status.classList.remove('app-error'); statusText.textContent = text; };
    const iconFor = { 'Open files…': 'folder', 'Open a sample…': 'layers', 'New diagram…': 'plus', 'Verify': 'check', 'Open': 'eye', 'Apply source': 'pen', 'Reload source': 'code', 'Download report': 'download', 'Download .ddn': 'download', 'Export SVG': 'download', 'Export PNG': 'download', 'Export JSON': 'download', 'Export Markdown': 'download', 'Export CSV': 'download', 'Download assets': 'download', 'Keyboard shortcuts': 'info' };
    const makeButton = (text, action, host = tools) => {
        const result = doc.createElement('button');
        result.type = 'button';
        result.textContent = text;
        if (iconFor[text])
            result.prepend((0, ui_icons_js_1.uiIcon)(doc, iconFor[text]));
        if (['Verify', 'Open', 'Apply source'].includes(text))
            result.classList.add('app-primary');
        result.addEventListener('click', () => { Promise.resolve().then(action).catch(showError); });
        host.append(result);
        return result;
    };
    const labelled = (label, control, host = tools) => { const tag = doc.createElement('label'); tag.append(doc.createTextNode(label), control); host.append(tag); return tag; };
    const themeChoice = doc.createElement('select');
    themeChoice.setAttribute('aria-label', 'Interface theme');
    themeChoice.title = 'Interface theme — colours of the tools, not the diagram';
    for (const name of ui_theme_js_1.UI_THEME_NAMES)
        themeChoice.add(new Option(name.charAt(0).toUpperCase() + name.slice(1), name));
    themeChoice.value = interfaceTheme;
    const saveInterface = () => {
        (0, ui_theme_js_1.setUITheme)(doc.body, interfaceTheme, interfaceTokens);
        doc.dispatchEvent(new CustomEvent('ddn:interface-theme', { detail: { name: interfaceTheme } }));
        try {
            localStorage.setItem('ddn.interface.v1', JSON.stringify({ name: interfaceTheme, overrides: interfaceTokens }));
        }
        catch {
            notify('Interface style changed for this session. Browser preference storage is unavailable.');
        }
    };
    themeChoice.addEventListener('change', () => { interfaceTheme = themeChoice.value; interfaceTokens = {}; saveInterface(); });
    const themeLabel = doc.createElement('label');
    const themeWord = doc.createElement('span');
    themeWord.className = 'app-theme-word';
    themeWord.textContent = 'Theme ';
    themeLabel.append(themeWord, themeChoice);
    interfaceControls.append(themeLabel);
    const customise = doc.createElement('button');
    customise.type = 'button';
    customise.textContent = 'UI colours';
    customise.title = 'Customise the page, panel, text and accent colours of the tools';
    customise.prepend((0, ui_icons_js_1.uiIcon)(doc, 'palette'));
    interfaceControls.append(customise);
    customise.addEventListener('click', () => {
        const original = { ...interfaceTokens }, dialog = (0, dialogs_js_1.createStandardDialog)(doc.body, { title: 'Interface colours', modal: false });
        const note = doc.createElement('p');
        note.textContent = 'These colours change the tools, not the diagram or its exported appearance.';
        dialog.body.append(note);
        const fields = [];
        for (const [label, token] of [['Page', '--ddn-ui-bg'], ['Panels', '--ddn-ui-surface'], ['Text', '--ddn-ui-text'], ['Accent', '--ddn-ui-accent']]) {
            const input = (0, dialogs_js_1.colourField)(dialog.body, label, String(interfaceTokens[token] ?? getComputedStyle(doc.body).getPropertyValue(token).trim()));
            fields.push({ input, token });
            input.addEventListener('input', () => {
                try {
                    const next = { ...interfaceTokens, [token]: input.value };
                    (0, ui_theme_js_1.setUITheme)(doc.body, interfaceTheme, next);
                    interfaceTokens = next;
                    saveInterface();
                    dialog.showError('');
                }
                catch (error) {
                    dialog.showError(error);
                }
            });
        }
        const reset = doc.createElement('button');
        reset.type = 'button';
        reset.textContent = 'Revert colours';
        reset.addEventListener('click', () => {
            interfaceTokens = { ...original };
            saveInterface();
            for (const { input, token } of fields) {
                input.value = String(interfaceTokens[token] ?? getComputedStyle(doc.body).getPropertyValue(token).trim());
                (0, dialogs_js_1.syncColourField)(input);
            }
            dialog.showError('');
        });
        dialog.footer.prepend(reset);
    });
    panel.id = 'ddn-source-panel';
    const collapseSource = doc.createElement('button');
    collapseSource.type = 'button';
    collapseSource.className = 'app-source-collapse';
    collapseSource.setAttribute('aria-label', 'Hide source');
    collapseSource.title = 'Collapse the source drawer to a rail, widening the diagram (Ctrl+\\)';
    collapseSource.append((0, ui_icons_js_1.uiIcon)(doc, 'arrow-left'));
    collapseSource.setAttribute('aria-expanded', 'true');
    collapseSource.setAttribute('aria-controls', panel.id);
    sourceHeading.append(collapseSource);
    const rail = doc.createElement('div');
    rail.className = 'app-rail';
    const expandSource = doc.createElement('button');
    expandSource.type = 'button';
    expandSource.append((0, ui_icons_js_1.uiIcon)(doc, 'code'), doc.createTextNode('Source'));
    expandSource.setAttribute('aria-label', 'Show source');
    expandSource.title = 'Open the source drawer (Ctrl+\\)';
    expandSource.setAttribute('aria-expanded', 'false');
    expandSource.setAttribute('aria-controls', panel.id);
    rail.append(expandSource);
    const splitter = doc.createElement('div');
    splitter.className = 'app-splitter';
    splitter.tabIndex = 0;
    splitter.setAttribute('role', 'separator');
    splitter.setAttribute('aria-orientation', 'vertical');
    splitter.setAttribute('aria-label', 'Source drawer width');
    splitter.setAttribute('aria-controls', panel.id);
    splitter.title = 'Drag to resize the source drawer, or focus and use the arrow keys';
    main.prepend(rail);
    panel.after(splitter);
    const VIEW_KEY = 'ddn.view.v1';
    const viewPrefs = (() => {
        try {
            return JSON.parse(localStorage.getItem(VIEW_KEY) ?? '{}') ?? {};
        }
        catch {
            return {};
        }
    })();
    const saveViewPrefs = () => {
        try {
            localStorage.setItem(VIEW_KEY, JSON.stringify(viewPrefs));
        }
        catch { }
    };
    const setSourceWidth = (width, persist = true) => {
        const limit = Math.max(260, Math.min(900, (doc.defaultView?.innerWidth ?? 1200) * .6));
        const value = Math.round(Math.max(220, Math.min(limit, width)));
        main.style.setProperty('--ddn-source-width', value + 'px');
        splitter.setAttribute('aria-valuenow', String(value));
        splitter.setAttribute('aria-valuemin', '220');
        splitter.setAttribute('aria-valuemax', String(Math.round(limit)));
        if (persist) {
            viewPrefs.sourceWidth = value;
            saveViewPrefs();
        }
    };
    setSourceWidth(viewPrefs.sourceWidth ?? 340, false);
    let splitDrag;
    splitter.addEventListener('pointerdown', event => {
        if (event.button !== 0)
            return;
        splitDrag = { id: event.pointerId, x: event.clientX, width: panel.getBoundingClientRect().width };
        splitter.setPointerCapture(event.pointerId);
        splitter.dataset.dragging = '';
        event.preventDefault();
    });
    splitter.addEventListener('pointermove', event => {
        if (splitDrag?.id === event.pointerId)
            setSourceWidth(splitDrag.width + event.clientX - splitDrag.x, false);
    });
    const endSplit = () => {
        if (!splitDrag)
            return;
        splitDrag = undefined;
        delete splitter.dataset.dragging;
        setSourceWidth(panel.getBoundingClientRect().width);
    };
    splitter.addEventListener('pointerup', endSplit);
    splitter.addEventListener('pointercancel', endSplit);
    splitter.addEventListener('keydown', event => {
        const step = event.shiftKey ? 64 : 16, current = panel.getBoundingClientRect().width;
        if (event.key === 'ArrowLeft') {
            event.preventDefault();
            setSourceWidth(current - step);
        }
        else if (event.key === 'ArrowRight') {
            event.preventDefault();
            setSourceWidth(current + step);
        }
        else if (event.key === 'Home') {
            event.preventDefault();
            setSourceWidth(220);
        }
        else if (event.key === 'End') {
            event.preventDefault();
            setSourceWidth(900);
        }
    });
    const showSource = (hidden, persist = false) => {
        if (detachedPanels.has('source')) {
            if (!hidden)
                detachedPanels.get('source').focus();
            return;
        }
        main.dataset.sourceHidden = String(hidden);
        collapseSource.setAttribute('aria-expanded', String(!hidden));
        expandSource.setAttribute('aria-expanded', String(!hidden));
        if (persist) {
            viewPrefs.sourceHidden = hidden;
            saveViewPrefs();
        }
        refreshMenus();
    };
    const detachedPanels = new Map();
    let refreshMenus = () => { };
    const narrow = !!doc.defaultView?.matchMedia('(max-width:750px)').matches;
    showSource(!isVerifier && (narrow || viewPrefs.sourceHidden === true));
    collapseSource.addEventListener('click', () => {
        if (detachedPanels.has('source')) {
            setPanelMode(panelOf('source'), 'hidden');
            return;
        }
        showSource(true, true);
        surface.querySelector('.ddn-viewer-stage>svg')?.focus({ preventScroll: true });
    });
    expandSource.addEventListener('click', () => { showSource(false, true); editor.focus({ preventScroll: true }); });
    tools.id = 'ddn-document-tools';
    tools.dataset.expanded = 'false';
    const documentToggle = doc.createElement('button');
    documentToggle.className = 'app-document-toggle';
    documentToggle.type = 'button';
    documentToggle.append((0, ui_icons_js_1.uiIcon)(doc, 'folder'), doc.createTextNode('Document tools'));
    documentToggle.setAttribute('aria-controls', tools.id);
    documentToggle.setAttribute('aria-expanded', 'false');
    interfaceControls.append(documentToggle);
    documentToggle.addEventListener('click', () => { const expanded = tools.dataset.expanded !== 'true'; tools.dataset.expanded = String(expanded); documentToggle.setAttribute('aria-expanded', String(expanded)); });
    const fileSelect = doc.createElement('select');
    fileSelect.setAttribute('aria-label', 'Source file');
    fileSelect.title = 'Which file of the document the source panel shows';
    function refreshFiles() {
        fileSelect.replaceChildren();
        for (const name of files.keys()) {
            const option = doc.createElement('option');
            option.value = name;
            option.textContent = name;
            fileSelect.append(option);
        }
        fileSelect.value = entry;
        fileSelect.parentElement.hidden = files.size < 2;
        refreshSourceState();
    }
    function refreshSourceState() {
        editor.readOnly = factories.mode === 'viewer' || files.get(entry)?.writable === false;
        sourceKind.textContent = editor.readOnly ? 'Read only' : 'Source';
        applyButton.disabled = isDesigner && editor.readOnly;
    }
    const input = doc.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.hidden = true;
    input.accept = '.ddn,.txt,.css,.svg,.png,.jpg,.jpeg,.webp,.json,.geojson';
    tools.append(input);
    async function loadSources(sources, incomingAssets, stillWanted = () => true, approvedContent = contentState()) {
        const operation = ++openGeneration;
        let encoded;
        try {
            encoded = await Promise.all([...(incomingAssets ?? [])].filter(([id]) => !sources.files.some(file => file.id === id)).map(async ([id, file]) => (0, document_draft_js_1.encodeDraftAsset)(id, file.type, new Uint8Array(await file.arrayBuffer()))));
        }
        catch (error) {
            if (operation === openGeneration)
                showError(error);
            return false;
        }
        if (operation !== openGeneration || !stillWanted())
            return false;
        if (contentState() !== approvedContent) {
            if (!await confirmReplace())
                return false;
            if (operation !== openGeneration || !stillWanted())
                return false;
        }
        clearRecovery();
        resetSession();
        replacing = true;
        files.clear();
        assets.clear();
        draftAssets = encoded;
        for (const [id, file] of incomingAssets ?? [])
            assets.set(id, file);
        for (const file of sources.files)
            files.set(file.id, { ...file, revision: String(++sequence) });
        lastOpened = { sources, assets: new Map(incomingAssets ?? []) };
        entry = documentEntry = sources.entry;
        refreshFiles();
        editor.value = files.get(entry)?.text ?? '';
        editorDirty = false;
        sourceConflict = false;
        pendingDocument = true;
        editGeneration++;
        renderDiagnostics([]);
        markClean();
        return true;
    }
    async function readFiles(selected) {
        let operation = ++openGeneration;
        const approvedContent = contentState();
        try {
            const loaded = [], selectedAssets = new Map();
            for (const file of Array.from(selected)) {
                const id = (0, index_js_1.normalizeLocation)(file.webkitRelativePath || file.name);
                if (selectedAssets.has(id))
                    throw Error('Duplicate selected file: ' + id);
                selectedAssets.set(id, file);
                if (!/\.(ddn|txt|css)$/i.test(id))
                    continue;
                if (file.size > 16 * 1024 * 1024)
                    throw Error('Source exceeds the 16 MiB per-file budget');
                const bytes = new Uint8Array(await file.arrayBuffer());
                if (operation !== openGeneration)
                    return;
                const text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
                loaded.push({ id, text, revision: '0', encoding: 'utf-8', writable: true, originalBytes: bytes });
            }
            const root = loaded.find(file => !/\.css$/i.test(file.id));
            if (!root)
                throw Error('Select at least one DDN source file (.ddn)');
            if (operation !== openGeneration)
                return;
            if (!await loadSources({ entry: root.id, files: loaded }, selectedAssets, () => true, approvedContent))
                return;
            const opening = operation = openGeneration + 1;
            const loadedContent = contentState();
            await open(true);
            if (opening !== openGeneration)
                return;
            if (contentState() === loadedContent)
                markClean();
            rememberRecent(entry.split('/').at(-1) ?? entry, workingSources());
            toast('Opened ' + entry);
        }
        catch (error) {
            if (operation === openGeneration)
                throw error;
        }
    }
    const confirmReplace = (includeRecovery = true) => new Promise(resolve => {
        if ((!dirty && (!includeRecovery || !pendingRecovery)) || !isDesigner) {
            resolve(true);
            return;
        }
        let decided = false;
        const dialog = (0, dialogs_js_1.createStandardDialog)(doc.body, { title: 'Replace your unsaved changes?', applyLabel: 'Replace', cancelLabel: 'Keep editing', onApply() { decided = true; }, onClose() { setTimeout(() => resolve(decided), 0); } });
        const text = doc.createElement('p');
        text.textContent = 'Replacing this document also replaces its recovery draft in this browser. Download any changes you want to keep first.';
        dialog.body.append(text);
        const downloadFirst = doc.createElement('button');
        downloadFirst.type = 'button';
        downloadFirst.textContent = 'Download .ddn first';
        downloadFirst.addEventListener('click', () => { Promise.resolve().then(downloadSource).catch(showError); });
        dialog.footer.prepend(downloadFirst);
    });
    const openFiles = async () => {
        if (await confirmReplace())
            input.click();
    };
    input.addEventListener('change', () => {
        if (input.files)
            void readFiles(input.files).catch(showError);
    });
    const newDocument = async () => {
        if (!await confirmReplace())
            return;
        if (!await loadSources({ entry: 'main.ddn', files: [{ id: 'main.ddn', text: '', revision: '0', encoding: 'utf-8', writable: true }] }))
            return;
        input.value = '';
        viewSelect.replaceChildren();
        const currentViewer = viewer, operation = openGeneration + 1, emptyContent = contentState();
        await open(true);
        if (!currentViewer || viewer !== currentViewer || operation !== openGeneration)
            return;
        if (contentState() !== emptyContent)
            return;
        markClean();
        factories.newDiagram?.(currentViewer, async (text) => {
            if (viewer !== currentViewer || operation !== openGeneration || contentState() !== emptyContent)
                throw Error('This document has changed. Start a new document again.');
            editor.value = text;
            editGeneration++;
            editorDirty = true;
            const creating = openGeneration + 1;
            await open(true);
            if (viewer !== currentViewer || creating !== openGeneration)
                throw Error('This document is no longer open.');
            setDirty(true);
            scheduleDraft();
        });
        notify('Create a workarea or a standalone view.');
    };
    const catalogue = () => { const site = host?.DDN_WEBSITE_CATALOGUE; return site && Array.isArray(site.corpus) ? site.corpus : []; };
    const loadSampleScript = (sampleEntry) => new Promise((resolve, reject) => {
        if (!host || !catalogue().some(sample => sample.entry === sampleEntry)) {
            reject(Error('Unknown sample'));
            return;
        }
        const script = doc.createElement('script');
        const previous = host.DDN_SITE_INITIAL;
        script.src = new URL('../' + sampleEntry + '.js', host.location.href).href;
        script.onload = () => {
            const initial = host.DDN_SITE_INITIAL;
            script.remove();
            if (previous !== undefined)
                host.DDN_SITE_INITIAL = previous;
            else
                delete host.DDN_SITE_INITIAL;
            if (!initial?.sources)
                reject(Error('The sample did not supply sources'));
            else
                resolve(initial);
        };
        script.onerror = () => { script.remove(); reject(Error('Unable to load the sample ' + sampleEntry)); };
        doc.body.append(script);
    });
    const openSampleDialog = async () => {
        if (!await confirmReplace())
            return;
        let chosen = { kind: 'starter', name: 'ERD whiteboard' };
        let sampleOpen = true;
        const dialog = (0, dialogs_js_1.createStandardDialog)(doc.body, { title: 'Open a sample', applyLabel: 'Open', onClose() { sampleOpen = false; }, async onApply() {
                const approvedContent = contentState();
                if (chosen.kind === 'starter') {
                    if (!await loadSources({ entry: 'main.ddn', files: [{ id: 'main.ddn', text: examples[chosen.name], revision: '0', encoding: 'utf-8', writable: true }] }, undefined, () => sampleOpen))
                        return;
                }
                else {
                    const operation = ++openGeneration;
                    const initial = await loadSampleScript(chosen.entry);
                    if (operation !== openGeneration || !sampleOpen)
                        return;
                    if (!await loadSources(initial.sources, new Map(Object.entries(initial.assets ?? {}).map(([id, asset]) => [id, new File([asset.text], id, { type: asset.mime })])), () => sampleOpen, approvedContent))
                        return;
                }
                const operation = openGeneration + 1;
                const loadedContent = contentState();
                await open(true);
                if (operation !== openGeneration || !sampleOpen)
                    return;
                if (contentState() === loadedContent)
                    markClean();
                rememberRecent(chosen.kind === 'starter' ? chosen.name : chosen.title, workingSources());
                toast('Opened sample: ' + (chosen.kind === 'starter' ? chosen.name : chosen.title));
            } });
        const search = doc.createElement('input');
        search.type = 'search';
        search.placeholder = 'Filter samples';
        search.setAttribute('aria-label', 'Filter samples');
        dialog.body.append(search);
        const list = doc.createElement('div');
        list.className = 'app-samples';
        list.setAttribute('role', 'listbox');
        dialog.body.append(list);
        const hint = doc.createElement('p');
        hint.textContent = 'Starters are small documents to edit; field-guide samples show finished diagrams of each type. Opening a sample replaces the current document.';
        dialog.body.append(hint);
        const render = () => {
            const q = search.value.trim().toLowerCase();
            list.replaceChildren();
            const section = (title) => { const head = doc.createElement('div'); head.className = 'app-menu-head'; head.textContent = title; list.append(head); };
            const option = (label, detail, value, pressed) => {
                const item = doc.createElement('button');
                item.type = 'button';
                item.setAttribute('role', 'option');
                item.setAttribute('aria-pressed', String(pressed));
                item.setAttribute('aria-selected', String(pressed));
                item.append(doc.createTextNode(label));
                if (detail) {
                    const small = doc.createElement('small');
                    small.textContent = detail;
                    item.append(small);
                }
                item.addEventListener('click', () => { chosen = value; render(); });
                item.addEventListener('dblclick', () => { chosen = value; dialog.applyButton?.click(); });
                list.append(item);
            };
            const starters = Object.keys(examples).filter(name => !q || name.toLowerCase().includes(q));
            if (starters.length) {
                section('Starters');
                for (const name of starters)
                    option(name, 'starter', { kind: 'starter', name }, chosen.kind === 'starter' && chosen.name === name);
            }
            const corpus = catalogue().filter(item => !q || `${item.title} ${item.entry} ${(item.views ?? []).map(v => v.profile).join(' ')}`.toLowerCase().includes(q));
            if (corpus.length) {
                section('Field guide samples');
                for (const item of corpus.slice(0, 200))
                    option(item.title ?? item.entry, `${(item.views ?? []).length} view${(item.views ?? []).length === 1 ? '' : 's'} · ${(item.views ?? [])[0]?.profile ?? ''}`, { kind: 'catalogue', entry: item.entry, title: item.title ?? item.entry }, chosen.kind === 'catalogue' && chosen.entry === item.entry);
            }
            if (!starters.length && !corpus.length) {
                const empty = doc.createElement('p');
                empty.textContent = 'No sample matches.';
                list.append(empty);
            }
        };
        search.addEventListener('input', render);
        render();
    };
    doc.addEventListener('ddn:open-sample', () => { void openSampleDialog().catch(showError); });
    doc.addEventListener('ddn:open-files', () => { void openFiles().catch(showError); });
    doc.addEventListener('ddn:new-document', () => { void newDocument().catch(showError); });
    labelled('File', fileSelect);
    const viewSelect = doc.createElement('select');
    viewSelect.setAttribute('aria-label', 'Current view');
    viewSelect.title = 'Which view of the document the diagram shows';
    if (!isVerifier)
        labelled('View', viewSelect);
    viewSelect.addEventListener('change', () => {
        if (viewer && viewSelect.value)
            void viewer.navigate({ kind: 'fit-view', target: JSON.parse(viewSelect.value) }).catch(showError);
    });
    fileSelect.addEventListener('change', () => {
        if (editorDirty) {
            fileSelect.value = entry;
            showError('Apply the source edit before switching files.');
            return;
        }
        entry = fileSelect.value;
        editor.value = files.get(entry)?.text ?? '';
        refreshSourceState();
        validateSoon();
    });
    const level = doc.createElement('select');
    level.setAttribute('aria-label', 'Verification level');
    for (const value of ['decode', 'structural', 'semantic', 'review', 'publication']) {
        const option = doc.createElement('option');
        option.value = value;
        option.textContent = value;
        level.append(option);
    }
    level.value = 'semantic';
    const purpose = doc.createElement('input');
    purpose.value = 'design';
    purpose.setAttribute('aria-label', 'Verification purpose');
    purpose.size = 12;
    if (isVerifier) {
        labelled('Level', level);
        labelled('Purpose', purpose);
    }
    const spacer = doc.createElement('span');
    spacer.className = 'app-spacer';
    tools.append(spacer);
    const dirtyLabel = doc.createElement('span');
    dirtyLabel.className = 'app-dirty';
    dirtyLabel.setAttribute('aria-live', 'polite');
    const applyHost = isDesigner ? sourceToolbar : tools;
    const applyButton = makeButton(isVerifier ? 'Verify' : factories.mode === 'viewer' ? 'Open' : 'Apply source', () => open(), applyHost);
    applyButton.title = isDesigner ? 'Apply the source text to the diagram (Ctrl+Enter)' : isVerifier ? 'Verify the source text' : 'Open the source text in the viewer';
    if (isDesigner) {
        const reload = makeButton('Reload source', () => {
            const current = viewer && factories.getRuntime?.(viewer).sources();
            if (current) {
                syncSources(current);
                notify('Source reloaded from the current diagram.');
            }
        }, sourceToolbar);
        reload.title = 'Rewrite the source text from the current diagram (keeps your diagram, discards unapplied text edits)';
        sourceToolbar.append(dirtyLabel);
    }
    const cancelButton = makeButton('Cancel', () => {
        if (cancellation) {
            cancellation.aborted = true;
            for (const listener of cancellation.listeners)
                listener();
            notify('Cancellation requested');
        }
    }, isDesigner ? sourceToolbar : tools);
    cancelButton.title = 'Stop a long-running open or verification';
    cancelButton.hidden = true;
    const download = (name, blob) => { const url = URL.createObjectURL(blob), a = doc.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); toast('Download requested: ' + name); notify('Download requested: ' + name + '.'); };
    const downloadSource = async () => {
        if (isVerifier) {
            if (!lastReport)
                throw Error('Verify a document first');
            download('ddn-verification.json', new Blob([JSON.stringify(lastReport, null, 2)], { type: 'application/json' }));
            return;
        }
        const source = workingSources(), saved = contentState(), generation = editGeneration, currentViewer = viewer;
        if (designer && !editorDirty && !sourceConflict && !pendingDocument) {
            const artifacts = await designer.save();
            if (viewer !== currentViewer)
                return;
            for (const artifact of artifacts)
                download(artifact.name, artifact.blob);
        }
        else {
            for (const file of source.files)
                download(file.id, new Blob([file.originalBytes ? new Uint8Array(file.originalBytes) : file.text], { type: 'text/plain;charset=utf-8' }));
        }
        if (generation === editGeneration && saved === contentState()) {
            cleanState = saved;
            setDirty(false);
        }
        rememberRecent(documentEntry.split('/').at(-1) ?? documentEntry, source);
        persistDraft();
    };
    let captureScope = 'view';
    const captureTarget = () => {
        if (captureScope === 'selection') {
            const selected = (0, ui_commands_js_1.findUICommand)(surface, 'view.selection')?.value?.();
            if (selected)
                return { kind: 'item', target: JSON.parse(selected) };
        }
        if (captureScope === 'workarea' && !standaloneDocument() || !viewSelect.value)
            return { kind: 'workarea' };
        return { kind: 'view', target: JSON.parse(viewSelect.value) };
    };
    const exportAs = (format) => async () => {
        if (!viewer)
            throw Error('Open a document first');
        const result = await viewer.capture({ scope: captureTarget(), format, extent: 'content', includePreview: false, partial: format === 'svg' ? 'label' : 'reject', stale: 'reject' });
        if (!result.ok)
            throw Error(result.diagnostics.map(d => d.message).join('; ') || result.reason);
        for (const artifact of result.artifacts)
            download(artifact.name, artifact.blob);
    };
    const downloadAssets = () => {
        const supplied = [...assets].filter(([id]) => !files.has(id));
        if (!supplied.length) {
            toast('This document has no separately supplied assets (images, CSS, GeoJSON).');
            return;
        }
        for (const [id, file] of supplied)
            download(id.split('/').at(-1) ?? id, file);
    };
    const saveBundle = async () => {
        if (isVerifier)
            throw Error('Bundles are for documents; use Download report.');
        const currentViewer = viewer, entries = [];
        if (designer && !editorDirty && !sourceConflict && !pendingDocument) {
            for (const artifact of await designer.save())
                entries.push({ name: artifact.name, bytes: new Uint8Array(await artifact.blob.arrayBuffer()) });
        }
        else
            for (const file of workingSources().files)
                entries.push({ name: file.id, bytes: file.originalBytes ? new Uint8Array(file.originalBytes) : new TextEncoder().encode(file.text) });
        if (viewer !== currentViewer)
            return;
        for (const [id, file] of assets)
            if (!files.has(id) && !entries.some(entry => entry.name === id))
                entries.push({ name: id, bytes: new Uint8Array(await file.arrayBuffer()) });
        const base = documentEntry.split('/').at(-1)?.replace(/\.ddn$/i, '') || 'document';
        download(base + '.zip', (0, zip_js_1.zipFiles)(entries));
        persistDraft();
    };
    function showShortcuts() {
        const dialog = (0, dialogs_js_1.createStandardDialog)(doc.body, { title: 'Keyboard shortcuts' });
        const dl = doc.createElement('dl');
        dl.className = 'app-shortcuts';
        const rows = [['Ctrl+K', 'Command search: find any menu command'], ['Ctrl+Z / Ctrl+Shift+Z or Ctrl+Y', 'Undo / redo'], ['Ctrl+X / Ctrl+C / Ctrl+V', 'Cut / copy / paste the selected element'], ['Ctrl+Shift+V / Ctrl+Alt+V', 'Paste in place / paste as reference'], ['Ctrl+D', 'Duplicate the selected element'], ['Delete', 'Delete the selected element'], ['Arrow keys', 'Move the selected element 16 px (Shift: 1 px; snaps to the grid when snapping is on)'], ['Enter', 'Select the focused element'], ['Escape', 'Cancel a drag, close a menu or dialog, clear the selection'], ['Ctrl+= / Ctrl+− / Ctrl+0', 'Zoom in / out / actual size'], ['Shift+1 / Shift+2 / Shift+3', 'Fit workarea / fit selection / fit current view'], ['Alt+← / Alt+→', 'Previous / next position'], ['+ / − / 0', 'Zoom in / out / fit the workarea (diagram focused)'], ['Mouse wheel', 'Designer: scroll the workarea (Ctrl+wheel or pinch zooms) · Viewer: zoom at the pointer'], ['A', 'Add element (opens the palette)'], ['C', 'Connect: click the first element, then the second'], ['P', 'Properties of the selected element (inspector)'], ['F2', 'Rename the selected element'], ['Double-click', 'Rename an element'], ['Right-click / long-press', 'Context menu for the element'], ['Ctrl+Enter', 'Apply the source text'], ['Ctrl+S / Ctrl+Shift+S', 'Download the .ddn source / the whole document as a .zip'], ['Ctrl+O', 'Open files'], ['Ctrl+Alt+N', 'New diagram'], ['Ctrl+F', 'Find a view or element'], ['Ctrl+\\', 'Collapse or open the source drawer'], ['Ctrl+I', 'Show or hide the inspector'], ['Ctrl+Shift+E', 'Show or hide the navigator'], ['Ctrl+E / Ctrl+P', 'Export / print the current document view'], ['F1', 'Open the guide'], ['Esc then Tab', 'Leave the source editor'], ['?', 'This list']];
        for (const [keys = '', text = ''] of rows) {
            const dt = doc.createElement('dt'), dd = doc.createElement('dd');
            dt.textContent = keys;
            dd.textContent = text;
            dl.append(dt, dd);
        }
        dialog.body.append(dl);
    }
    doc.addEventListener('ddn:shortcuts', showShortcuts);
    const lineOf = (text, offset) => text.slice(0, Math.max(0, offset)).split('\n').length;
    const renderDiagnostics = (items) => {
        diagnosticsList.replaceChildren();
        const problems = items.filter(d => d.severity === 'error' || d.severity === 'warning').slice(0, 20);
        editor.setAttribute('aria-invalid', String(problems.some(d => d.severity === 'error')));
        for (const d of problems) {
            const row = doc.createElement('button');
            row.type = 'button';
            row.setAttribute('role', 'listitem');
            const offset = d.source && (d.source.file === entry || !d.source.file) ? Number(d.source.start) : undefined;
            const line = offset !== undefined && Number.isFinite(offset) ? lineOf(editor.value, offset) : undefined;
            const where = doc.createElement('b');
            where.textContent = line ? `Line ${line}` : d.severity === 'error' ? 'Error' : 'Warning';
            row.append(where, doc.createTextNode(d.message));
            row.title = offset !== undefined && Number.isFinite(offset) ? 'Go to this line in the source' : d.code ?? '';
            row.addEventListener('click', () => {
                if (offset !== undefined && Number.isFinite(offset)) {
                    editor.focus();
                    editor.setSelectionRange(offset, offset);
                    const before = editor.value.slice(0, offset).split('\n').length;
                    editor.scrollTop = Math.max(0, (before - 4) * 19.2);
                }
            });
            diagnosticsList.append(row);
        }
    };
    let validateTimer;
    const validateNow = () => {
        if (isVerifier)
            return;
        try {
            const decoded = (0, index_js_2.decodeSources)(workingSources());
            renderDiagnostics(decoded.diagnostics);
        }
        catch {
        }
    };
    const validateSoon = () => { clearTimeout(validateTimer); validateTimer = setTimeout(validateNow, 600); };
    editor.addEventListener('input', () => { editorDirty = true; editGeneration++; setDirty(contentState() !== cleanState); validateSoon(); scheduleDraft(); });
    let draftTimer;
    function persistDraft() {
        if (!isDesigner || pendingRecovery || replacing)
            return;
        try {
            const source = workingSources();
            const snapshot = { ...source, files: source.files.map(({ id, text, writable }) => ({ id, text, writable, revision: 'recovered', encoding: 'utf-8' })), version: 1, savedAt: new Date().toISOString(), assets: draftAssets };
            localStorage.setItem(document_draft_js_1.DRAFT_KEY, JSON.stringify(snapshot));
            savedIndicator.textContent = 'Kept in this browser · ' + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }
        catch {
            savedIndicator.textContent = 'Browser storage unavailable — download to keep your work';
        }
    }
    function scheduleDraft() {
        if (!isDesigner || pendingRecovery || replacing)
            return;
        clearTimeout(draftTimer);
        draftTimer = setTimeout(persistDraft, 800);
    }
    const assetProvider = { async read(id) {
            let location = id;
            try {
                const parts = JSON.parse(id);
                if (Array.isArray(parts)) {
                    const recordId = String(parts[1]);
                    const snapshot = viewer && factories.getRuntime?.(viewer).snapshot();
                    const bundle = snapshot?.normalized;
                    const record = bundle?.files?.find(f => f.location === parts[0])?.document.assets?.find(a => a.id === recordId || a.name === recordId);
                    location = record && typeof record.path === 'string' ? record.path : (0, index_js_1.normalizeLocation)(recordId, String(parts[0]));
                }
            }
            catch { }
            const file = assets.get(location);
            if (!file)
                throw Error('Local asset was not supplied: ' + location);
            const bytes = new Uint8Array(await file.arrayBuffer());
            const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
            return { bytes, mime: file.type || (/\.svg$/i.test(location) ? 'image/svg+xml' : /\.css$/i.test(location) ? 'text/css' : /\.(geojson|json)$/i.test(location) ? 'application/geo+json' : 'application/octet-stream'), hash: Array.from(digest, b => b.toString(16).padStart(2, '0')).join('') };
        } };
    let unsubscribe;
    function attachViewer() {
        if (!factories.viewer)
            return;
        const attached = factories.viewer(surface, { runtimeOptions: factories.options(), assets: assetProvider });
        viewer = attached;
        if (factories.designer)
            designer = factories.designer(attached);
        attached.subscribe(event => {
            if (attached === viewer && event.kind === 'diagnostics' && event.diagnostics?.length)
                notify(event.diagnostics.map(d => d.message).join(' · '));
        });
        const runtime = factories.getRuntime?.(attached);
        unsubscribe = runtime?.subscribe(event => {
            if (attached !== viewer || event.kind !== 'revision')
                return;
            const source = runtime.sources();
            if (!source)
                return;
            if (editorDirty) {
                sourceConflict = true;
                notify('The diagram changed while you were editing the source text. Reload source to see the change, then reapply your edit.');
            }
            else
                syncSources(source);
            const views = refreshViews(true);
            if (views?.newView) {
                viewSelect.value = views.newView;
                void attached.navigate({ kind: 'fit-view', target: JSON.parse(views.newView) }).catch(showError);
            }
            else if (views && [...viewSelect.options].some(option => option.value === views.previousView))
                viewSelect.value = views.previousView;
            if (!replacing) {
                setDirty(contentState() !== cleanState);
                if (dirty)
                    scheduleDraft();
            }
        });
    }
    function resetSession() {
        openGeneration++;
        clearTimeout(validateTimer);
        clearTimeout(draftTimer);
        if (cancellation) {
            cancellation.aborted = true;
            for (const listener of cancellation.listeners)
                listener();
        }
        unsubscribe?.();
        unsubscribe = undefined;
        for (const id of ['inspector', 'palette', 'navigator'])
            detachedPanels.get(id)?.dock();
        designer?.destroy();
        viewer?.destroy();
        designer = undefined;
        viewer = undefined;
        lastReport = undefined;
        knownViewKeys = new Set();
        viewSelect.replaceChildren();
        attachViewer();
    }
    function syncSources(source) {
        files.clear();
        for (const file of source.files)
            files.set(file.id, file);
        documentEntry = source.entry;
        if (!files.has(entry))
            entry = source.entry;
        refreshFiles();
        editor.value = files.get(entry)?.text ?? '';
        editorDirty = false;
        sourceConflict = false;
        renderDiagnostics([]);
    }
    let knownViewKeys = new Set();
    function refreshViews(selectNew = true) {
        if (!viewer)
            return;
        const runtime = factories.getRuntime?.(viewer);
        const previousView = viewSelect.value;
        viewSelect.replaceChildren();
        const bundle = runtime?.snapshot()?.normalized;
        const keys = new Set();
        let added;
        for (const file of bundle?.files ?? [])
            for (const view of file.document.views ?? []) {
                if (standaloneDocument() && viewSelect.options.length)
                    continue;
                const option = doc.createElement('option');
                option.value = JSON.stringify({ file: file.location, id: view.id });
                option.textContent = view.title ?? view.name ?? view.id;
                viewSelect.append(option);
                keys.add(option.value);
                if (!knownViewKeys.has(option.value))
                    added = option.value;
            }
        const newView = selectNew && knownViewKeys.size && added && !knownViewKeys.has(added) ? added : undefined;
        knownViewKeys = keys;
        viewSelect.parentElement.hidden = standaloneDocument() || viewSelect.options.length < 2;
        return { previousView, newView };
    }
    attachViewer();
    window.addEventListener('pagehide', () => {
        clearTimeout(draftTimer);
        clearTimeout(validateTimer);
        if (dirty)
            persistDraft();
        unsubscribe?.();
        designer?.destroy();
        viewer?.destroy();
        verifier?.destroy();
    }, { once: true });
    window.addEventListener('beforeunload', event => {
        if (isDesigner && dirty) {
            event.preventDefault();
            event.returnValue = '';
        }
    });
    function renderReport(report) {
        surface.replaceChildren();
        const body = doc.createElement('div');
        body.className = 'app-report';
        const heading = doc.createElement('h2');
        heading.textContent = report.outcome + ' — ' + (report.reviewEligible ? 'review eligible' : 'review not established');
        body.append(heading);
        const detail = doc.createElement('p');
        detail.textContent = `${report.level} · ${report.coverage.checked.length} checked records · ${Math.round(report.stats.elapsedMs)} ms`;
        body.append(detail);
        const search = doc.createElement('input');
        search.placeholder = 'Filter diagnostics';
        search.setAttribute('aria-label', 'Filter diagnostics');
        body.append(search);
        const table = doc.createElement('table');
        body.append(table);
        const fill = () => {
            table.replaceChildren();
            for (const diagnostic of report.diagnostics.filter(d => (d.code + ' ' + d.message).toLowerCase().includes(search.value.toLowerCase()))) {
                const row = doc.createElement('tr');
                for (const text of [diagnostic.severity, diagnostic.code, diagnostic.message, diagnostic.source ? diagnostic.source.file + ':' + diagnostic.source.start : '']) {
                    const cell = doc.createElement('td');
                    cell.textContent = text;
                    row.append(cell);
                }
                table.append(row);
            }
        };
        search.addEventListener('input', fill);
        fill();
        surface.append(body);
    }
    async function open(replace = false) {
        const operation = ++openGeneration, bufferGeneration = editGeneration;
        const currentViewer = viewer, currentDesigner = designer;
        try {
            replace = replace || pendingDocument;
            if (sourceConflict && !replace)
                throw Error('The diagram changed since this source edit began. Copy your text, then Reload source and reconcile your edit.');
            const old = files.get(entry);
            if (old?.text !== editor.value)
                files.set(entry, { id: entry, text: editor.value, revision: String(++sequence), encoding: 'utf-8', writable: old?.writable ?? true });
            const source = workingSources();
            if (cancellation) {
                cancellation.aborted = true;
                for (const listener of cancellation.listeners)
                    listener();
            }
            cancellation = { aborted: false, listeners: new Set() };
            const current = cancellation;
            const cancel = { get aborted() { return current.aborted; }, onAbort(handler) { current.listeners.add(handler); return () => { current.listeners.delete(handler); }; } };
            notify('Working…');
            cancelButton.hidden = false;
            await new Promise(resolve => setTimeout(resolve, 0));
            if (operation !== openGeneration)
                return;
            if (factories.mode === 'verifier') {
                const report = await verifier.verifySources(source, { scope: { kind: 'workarea' }, purpose: purpose.value, level: level.value, cancel });
                if (operation !== openGeneration)
                    return;
                lastReport = report;
                renderDiagnostics(report.diagnostics.filter(d => d.source));
                renderReport(lastReport);
                notify('Verification ' + lastReport.outcome + (bufferGeneration !== editGeneration ? ' for the previous source buffer; verify the current edit again.' : ''));
            }
            else if (currentViewer) {
                const runtime = factories.getRuntime?.(currentViewer), currentSources = runtime?.sources();
                if (!replace && currentDesigner && currentSources && currentSources.entry === documentEntry && currentSources.files.length === source.files.length && currentSources.files.every(f => source.files.some(next => next.id === f.id))) {
                    const patches = source.files.flatMap(file => { const previous = currentSources.files.find(f => f.id === file.id); return previous.text === file.text ? [] : [{ file: file.id, base: previous.revision, start: 0, end: previous.text.length, text: file.text }]; });
                    if (patches.length) {
                        const prepared = await currentDesigner.commands.prepare({ kind: 'edit-source', patches }, { cancel });
                        if (operation !== openGeneration)
                            return;
                        if (bufferGeneration !== editGeneration) {
                            if (prepared.ok)
                                currentDesigner.commands.discard(prepared.command.id);
                            notify('Your newer source text is retained. Apply again to use the current edit.');
                            return;
                        }
                        if (!prepared.ok) {
                            renderDiagnostics(prepared.failure.diagnostics);
                            throw Error(prepared.failure.diagnostics.map(d => d.message).join('; '));
                        }
                        editorDirty = false;
                        const committed = await currentDesigner.commands.commit(prepared.command.id, { cancel });
                        if (operation !== openGeneration)
                            return;
                        if (!committed.ok) {
                            editorDirty = true;
                            renderDiagnostics(committed.failure.diagnostics);
                            throw Error(committed.failure.diagnostics.map(d => d.message).join('; '));
                        }
                    }
                }
                else {
                    editorDirty = false;
                    const result = await currentViewer.open(source, { cancel });
                    if (operation !== openGeneration)
                        return;
                    renderDiagnostics(result.diagnostics);
                    if (result.diagnostics.some(d => d.severity === 'error'))
                        throw Error(result.diagnostics.map(d => d.message).join(' · '));
                }
                if (operation !== openGeneration)
                    return;
                if (bufferGeneration !== editGeneration) {
                    sourceConflict = true;
                    notify('Your newer source text is retained. The completed operation used an earlier buffer; reconcile before applying.');
                    return;
                }
                const openedSources = runtime?.sources();
                if (openedSources)
                    syncSources(openedSources);
                pendingDocument = false;
                const views = refreshViews(false);
                const previousView = views?.previousView;
                const requested = factories.initial?.view;
                const chosen = [...viewSelect.options].find(o => o.value === previousView) ?? [...viewSelect.options].find(o => JSON.parse(o.value).id === requested) ?? viewSelect.options[0];
                if (chosen) {
                    viewSelect.value = chosen.value;
                    await currentViewer.navigate({ kind: 'fit-view', target: JSON.parse(chosen.value) });
                }
                if (operation !== openGeneration)
                    return;
                replacing = false;
                if (replace)
                    factories.ready?.({ viewer: currentViewer, ...(currentDesigner ? { designer: currentDesigner } : {}) });
                notify((factories.edition === 'complete' ? 'Complete' : 'Native') + ' DDN ' + factories.mode + ' ready');
            }
        }
        catch (error) {
            if (operation === openGeneration) {
                if (bufferGeneration === editGeneration)
                    editorDirty = true;
                throw error;
            }
        }
        finally {
            if (operation === openGeneration) {
                cancelButton.hidden = true;
                replacing = false;
            }
        }
    }
    let escapeArmed = 0;
    editor.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
            escapeArmed = Date.now();
            notify('Press Tab to leave the source editor.');
            return;
        }
        if (event.key === 'Tab' && !editor.readOnly) {
            if (Date.now() - escapeArmed < 3000) {
                escapeArmed = 0;
                return;
            }
            event.preventDefault();
            const start = editor.selectionStart;
            editor.setRangeText('    ', start, editor.selectionEnd, 'end');
            editorDirty = true;
            editGeneration++;
            setDirty(true);
            validateSoon();
            scheduleDraft();
        }
        if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && !editor.readOnly) {
            event.preventDefault();
            void open().catch(showError);
        }
    });
    const WEAVER = 'Available in ScratchWeaver, the commercial edition';
    const LATER = 'Planned for a later iteration of the designer';
    const command = (id) => (0, ui_commands_js_1.findUICommand)(surface, id);
    const runCommand = (id, argument) => {
        const found = command(id);
        if (!found || !(0, ui_commands_js_1.commandEnabled)(found))
            return false;
        Promise.resolve().then(() => found.run(argument)).catch(showError);
        return true;
    };
    const bus = (label, id, extra = {}) => ({
        label, ...(extra.shortcut ? { shortcut: extra.shortcut } : {}), hint: extra.hint ?? command(id)?.hint ?? (viewer ? 'Not available for the current selection or view' : 'Open a document first'),
        enabled: () => (0, ui_commands_js_1.commandEnabled)(command(id)), run: () => { runCommand(id, extra.argument); },
        ...(extra.checked ? { checked: extra.checked, radio: !!extra.radio } : {}),
    });
    const weaver = (label) => ({ label, badge: 'ScratchWeaver', hint: WEAVER, enabled: () => false });
    const later = (label, shortcut) => ({ label, hint: LATER, enabled: () => false, ...(shortcut ? { shortcut } : {}) });
    const separator = { kind: 'separator' };
    const heading = (label) => ({ kind: 'heading', label });
    const needsDesigner = (item) => isDesigner || item.kind === 'separator' || item.kind === 'heading' ? item : { ...item, enabled: () => false, hint: 'Editing happens in the designer' };
    function standaloneDocument() {
        const snapshot = viewer && factories.getRuntime?.(viewer)?.snapshot();
        return !!snapshot && (0, index_js_1.listRecords)(snapshot.normalized).some(record => record.kind === 'workarea' && record.file === snapshot.rootFile && record.record.mode === 'standalone');
    }
    const workareaOnly = new Set(['Workarea settings…', 'Add view…', 'Add document view…', 'New document view…', 'Place an existing view', 'Layers', 'Regions', 'Bookmarks', 'Workarea defaults…', 'Fit workarea', 'Expand view', 'Mini-views when small']);
    const documentItems = (items) => standaloneDocument() ? items.filter(item => item.kind === 'separator' || !workareaOnly.has(item.label)) : items;
    const RECENT_KEY = 'ddn.recent.v1';
    function readRecent() {
        try {
            const list = JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]');
            return Array.isArray(list) ? list.filter(item => item && typeof item.title === 'string' && item.sources && Array.isArray(item.sources.files)) : [];
        }
        catch {
            return [];
        }
    }
    function rememberRecent(title, sources) {
        if (!isDesigner)
            return;
        try {
            const compact = { entry: sources.entry, files: sources.files.map(({ id, text, writable }) => ({ id, text, writable, revision: 'recent', encoding: 'utf-8' })) };
            if (compact.files.reduce((sum, file) => sum + file.text.length, 0) > 512 * 1024 || !compact.files.some(file => file.text.trim()))
                return;
            localStorage.setItem(RECENT_KEY, JSON.stringify([{ title, savedAt: new Date().toISOString(), sources: compact }, ...readRecent().filter(item => item.title !== title)].slice(0, 6)));
        }
        catch { }
    }
    const openRecent = async (item) => {
        if (!await confirmReplace())
            return;
        if (!await loadSources(item.sources))
            return;
        const operation = openGeneration + 1, loaded = contentState();
        await open(true);
        if (operation === openGeneration && contentState() === loaded)
            markClean();
        toast('Opened ' + item.title);
    };
    const revert = async () => {
        const previous = lastOpened;
        if (!previous)
            throw Error('There is no opened version to return to yet.');
        if (!await confirmReplace(false))
            return;
        if (!await loadSources(previous.sources, previous.assets))
            return;
        const operation = openGeneration + 1, loaded = contentState();
        await open(true);
        if (operation === openGeneration && contentState() === loaded)
            markClean();
        toast('Reverted to the version you opened');
    };
    const importStylesheet = () => {
        const picker = doc.createElement('input');
        picker.type = 'file';
        picker.accept = '.css,text/css';
        picker.addEventListener('change', () => void (async () => {
            const file = picker.files?.[0];
            if (!file)
                return;
            if (editorDirty)
                throw Error('Apply or reload the source text before importing a stylesheet.');
            const name = (0, index_js_1.normalizeLocation)(file.name), text = await file.text();
            const root = files.get(documentEntry);
            if (!root)
                throw Error('The document has no root file.');
            files.set(name, { id: name, text, revision: String(++sequence), encoding: 'utf-8', writable: true });
            assets.set(name, file);
            const declaration = `style ${JSON.stringify(name)}\n`;
            if (!root.text.split('\n').some(line => line.trim() === declaration.trim())) {
                const updated = declaration + root.text;
                files.set(documentEntry, { ...root, text: updated, revision: String(++sequence) });
                if (entry === documentEntry)
                    editor.value = updated;
            }
            editGeneration++;
            editorDirty = false;
            pendingDocument = true;
            refreshFiles();
            await open(true);
            setDirty(true);
            scheduleDraft();
            toast('Stylesheet imported: ' + name);
        })().catch(showError));
        picker.click();
    };
    const printCurrent = async () => {
        if (!viewer)
            throw Error('Open a document first');
        const result = await viewer.capture({ scope: captureTarget(), format: 'svg', extent: 'content', includePreview: false, partial: 'label', stale: 'label' });
        if (!result.ok)
            throw Error(result.diagnostics.map(d => d.message).join('; ') || result.reason);
        const svgText = await result.artifacts[0].blob.text();
        const frame = doc.createElement('iframe');
        frame.setAttribute('aria-hidden', 'true');
        frame.tabIndex = -1;
        frame.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden';
        doc.body.append(frame);
        const printDoc = frame.contentDocument;
        printDoc.open();
        printDoc.write('<!doctype html><html lang="en"><head><meta charset="utf-8"><title></title><style>@page{margin:12mm}html,body{margin:0}svg{display:block;width:100%;height:auto;max-height:calc(100vh - 2px)}</style></head><body></body></html>');
        printDoc.close();
        printDoc.title = doc.title;
        const parsed = new DOMParser().parseFromString(svgText, 'image/svg+xml').documentElement;
        printDoc.body.append(printDoc.importNode(parsed, true));
        const win = frame.contentWindow;
        win.addEventListener('afterprint', () => setTimeout(() => frame.remove(), 0));
        setTimeout(() => frame.remove(), 120000);
        win.focus();
        win.print();
    };
    const chooseCaptureScope = () => {
        const chosen = standaloneDocument() && captureScope === 'workarea' ? 'view' : captureScope;
        const dialog = (0, dialogs_js_1.createStandardDialog)(doc.body, { title: 'Capture scope', modal: false });
        const note = doc.createElement('p');
        note.textContent = 'Exports and prints use an explicit scope, never "whatever is on screen". The choice lasts for this session.';
        dialog.body.append(note);
        const choice = (0, choice_field_js_1.choiceField)(dialog.body, 'Capture scope', [
            { value: 'view', label: 'Current view', preview: () => (0, ui_icons_js_1.uiIcon)(doc, 'fit-view') },
            ...(!standaloneDocument() ? [{ value: 'workarea', label: 'Whole workarea', description: 'Every view', preview: () => (0, ui_icons_js_1.uiIcon)(doc, 'fit') }] : []),
            { value: 'selection', label: 'Selected element', description: 'Falls back to the current view', preview: () => (0, ui_icons_js_1.uiIcon)(doc, 'select') },
        ], chosen);
        choice.addEventListener('change', () => { captureScope = choice.value; toast('Export scope updated.'); });
    };
    const siteLink = (path) => doc.querySelector('.app-site-nav') ? new URL('../' + path, doc.defaultView.location.href).href : undefined;
    const help = (label, path, shortcut) => ({ label, ...(shortcut ? { shortcut } : {}), hint: 'Part of the DDN website; open the designer from the website to use this link', enabled: () => !!siteLink(path), run: () => {
            const url = siteLink(path);
            if (url)
                doc.defaultView.open(url, '_blank', 'noopener');
        } });
    const openHelp = () => {
        const url = siteLink('guide/index.html');
        if (url)
            doc.defaultView.open(url, '_blank', 'noopener');
        else
            showShortcuts();
    };
    const showAbout = () => {
        const dialog = (0, dialogs_js_1.createStandardDialog)(doc.body, { title: 'About DDN' });
        const lines = [
            `DDN ${isDesigner ? 'Designer' : isVerifier ? 'Verifier' : 'Viewer'} · dialect ddn-next-1 · ${factories.edition === 'complete' ? 'complete profile edition' : 'native edition'}.`,
            'Everything runs in this browser. Nothing is uploaded; documents are kept only when you download them (a recovery copy stays in this browser).',
            'DDN is free and open-source software under GPL-2.0-or-later, sponsored by ScratchBird Software Inc. ScratchWeaver, the commercial edition, adds collaboration, live layout sharing, managed connectors, templates and more output formats with the same menus.',
        ];
        for (const text of lines) {
            const p = doc.createElement('p');
            p.textContent = text;
            dialog.body.append(p);
        }
        const link = doc.createElement('a');
        link.href = 'https://scratchbird.ca';
        link.target = '_blank';
        link.rel = 'noopener';
        link.textContent = 'scratchbird.ca';
        dialog.body.append(link);
    };
    const showWhatsNew = () => {
        const dialog = (0, dialogs_js_1.createStandardDialog)(doc.body, { title: "What's new" });
        const list = doc.createElement('ul');
        for (const text of ['A menu bar: File, Edit, WorkArea, View, Document, Window and Help, the same in every edition.', 'The source panel is a drawer: collapse it to a rail, drag its edge to resize it, float it or pop it out.', 'Pop-out windows for the source, inspector, palette, navigator and the appearance editors, for a second monitor.', 'Cut, copy, paste, paste in place, paste as reference and duplicate.', 'Zoom presets, actual size, fit selection, and a zoom control in the status bar.', 'View settings: grid, snap to grid, mini-views, mouse wheel behaviour, toolbar and status bar.', 'Documents: new document views, page setup, header and footer, export, capture scope and print.', 'Command search (Ctrl+K) finds any menu command.']) {
            const item = doc.createElement('li');
            item.textContent = text;
            list.append(item);
        }
        dialog.body.append(list);
    };
    const commandSearch = () => {
        const entries = [];
        const walk = (items, path) => {
            for (const item of items) {
                if (item.kind === 'separator' || item.kind === 'heading')
                    continue;
                if (item.kind === 'submenu') {
                    walk(item.items(), path + ' › ' + item.label);
                    continue;
                }
                entries.push({ path, item });
            }
        };
        for (const spec of menuSpecs)
            walk(spec.items(), spec.label);
        const dialog = (0, dialogs_js_1.createStandardDialog)(doc.body, { title: 'Command search' });
        const search = doc.createElement('input');
        search.type = 'search';
        search.placeholder = 'Type a command, e.g. "zoom" or "paste"';
        search.setAttribute('aria-label', 'Search commands');
        const list = doc.createElement('div');
        list.className = 'app-command-list';
        list.setAttribute('role', 'listbox');
        list.setAttribute('aria-label', 'Commands');
        dialog.body.append(search, list);
        let matches = [], active = 0;
        const usable = (item) => {
            try {
                return item.kind !== 'separator' && item.kind !== 'heading' && (!('enabled' in item) || !item.enabled || item.enabled());
            }
            catch {
                return false;
            }
        };
        const choose = (match) => {
            if (!match || !usable(match.item))
                return;
            dialog.close();
            Promise.resolve().then(() => match.item.run?.()).catch(showError);
        };
        const render = () => {
            const words = search.value.toLowerCase().split(/\s+/).filter(Boolean);
            matches = entries.filter(entry => usable(entry.item) && words.every(word => (entry.path + ' ' + entry.item.label).toLowerCase().includes(word))).slice(0, 60);
            active = Math.min(active, Math.max(0, matches.length - 1));
            list.replaceChildren();
            matches.forEach((match, index) => {
                const option = doc.createElement('button');
                option.type = 'button';
                option.setAttribute('role', 'option');
                option.setAttribute('aria-selected', String(index === active));
                const label = doc.createElement('span');
                label.textContent = match.item.label;
                const where = doc.createElement('small');
                where.textContent = match.path;
                option.append(label, where);
                if (match.item.shortcut) {
                    const kbd = doc.createElement('kbd');
                    kbd.textContent = match.item.shortcut;
                    option.append(kbd);
                }
                option.addEventListener('click', () => choose(match));
                list.append(option);
            });
            if (!matches.length) {
                const empty = doc.createElement('p');
                empty.textContent = 'No available command matches.';
                list.append(empty);
            }
        };
        search.addEventListener('input', () => { active = 0; render(); });
        search.addEventListener('keydown', event => {
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                active = (active + (event.key === 'ArrowDown' ? 1 : -1) + matches.length) % Math.max(1, matches.length);
                render();
                list.children[active]?.scrollIntoView({ block: 'nearest' });
            }
            else if (event.key === 'Enter') {
                event.preventDefault();
                choose(matches[active]);
            }
        });
        render();
        queueMicrotask(() => search.focus());
    };
    const applyViewSettings = (redraw = true) => {
        if (isDesigner)
            surface.dataset.ddnMenus = '';
        surface.dataset.ddnGrid = viewPrefs.grid ? 'on' : 'off';
        surface.dataset.ddnSnap = viewPrefs.snap ? 'on' : 'off';
        surface.dataset.ddnLod = viewPrefs.lod ?? 'auto';
        surface.dataset.ddnWheel = viewPrefs.wheel ?? (isDesigner ? 'pan' : 'zoom');
        if (viewPrefs.quick === false)
            surface.dataset.ddnQuick = 'hidden';
        else
            delete surface.dataset.ddnQuick;
        const navigator = (0, drawer_js_1.drawerFor)(surface.querySelector('.ddn-viewer'), 'navigator');
        if (navigator) {
            if (viewPrefs.outline === false && navigator.mode !== 'hidden')
                navigator.setMode('hidden');
            else if (viewPrefs.outline !== false && navigator.mode === 'hidden')
                navigator.setMode('docked');
        }
        if (viewPrefs.outline === false && !detachedPanels.has('navigator'))
            surface.dataset.ddnOutline = 'hidden';
        else if (!detachedPanels.has('navigator'))
            delete surface.dataset.ddnOutline;
        doc.body.dataset.ddnStatus = viewPrefs.status === false ? 'hidden' : 'shown';
        if (viewPrefs.motion)
            doc.body.dataset.ddnMotion = 'reduced';
        else
            delete doc.body.dataset.ddnMotion;
        if (viewPrefs.contrast)
            doc.body.dataset.ddnContrast = 'high';
        else
            delete doc.body.dataset.ddnContrast;
        if (redraw)
            runCommand('view.redraw');
    };
    const toggleSetting = (key) => { viewPrefs[key] = !viewPrefs[key]; saveViewPrefs(); applyViewSettings(); };
    const showSetting = (key) => { viewPrefs[key] = viewPrefs[key] === false; saveViewPrefs(); applyViewSettings(false); };
    const setting = (label, checked, change, shortcut) => ({ label, checked, run: change, ...(shortcut ? { shortcut } : {}) });
    const choice = (label, current, value, change) => ({ label, radio: true, checked: () => current() === value, run: () => change(value) });
    const setTheme = (name) => { themeChoice.value = name; themeChoice.dispatchEvent(new Event('change')); };
    doc.addEventListener('ddn:interface-theme', () => (0, popout_js_1.syncDetachedThemes)(doc));
    const toggleFullScreen = () => {
        if (doc.fullscreenElement)
            void doc.exitFullscreen();
        else
            void doc.documentElement.requestFullscreen?.().catch(() => toast('Full screen is not available here.', 'error'));
    };
    const viewerContainer = () => surface.querySelector('.ddn-viewer');
    const dockedIn = (selector, attribute) => ({
        element: () => surface.querySelector(selector),
        detaching: () => viewerContainer()?.removeAttribute(attribute),
        returned: () => {
            const container = viewerContainer();
            if (container?.querySelector(selector))
                container.setAttribute(attribute, '');
        },
    });
    const windowPanels = [
        { id: 'source', title: 'DDN source', element: () => panel, shown: () => main.dataset.sourceHidden !== 'true', show: () => showSource(false, true), hide: () => showSource(true, true),
            detaching: () => { main.dataset.sourceHidden = 'false'; main.dataset.sourceDetached = 'true'; }, returned: () => { delete main.dataset.sourceDetached; } },
        { id: 'inspector', title: 'Inspector', hostClass: 'ddn-viewer', ...dockedIn('.ddn-designer-dock-right', 'data-ddn-dock-right'), shown: () => !!surface.querySelector('.ddn-designer-dock-right'), show: () => {
                const found = command('window.inspector');
                if ((0, ui_commands_js_1.commandEnabled)(found))
                    void found.run(true);
            }, hide: () => { command('window.inspector')?.run(false); }, available: () => (0, ui_commands_js_1.commandEnabled)(command('window.inspector')), hint: 'Select an element first' },
        { id: 'palette', title: 'Element palette', hostClass: 'ddn-viewer', ...dockedIn('.ddn-designer-dock-left', 'data-ddn-dock-left'), shown: () => !!surface.querySelector('.ddn-designer-dock-left'), show: () => {
                const found = command('window.palette');
                if ((0, ui_commands_js_1.commandEnabled)(found))
                    void found.run(true);
            }, hide: () => { command('window.palette')?.run(false); }, available: () => (0, ui_commands_js_1.commandEnabled)(command('window.palette')), hint: 'This view type has no element palette' },
        { id: 'navigator', title: 'Navigator', hostClass: 'ddn-viewer', element: () => surface.querySelector('.ddn-viewer-outline'), shown: () => surface.dataset.ddnOutline !== 'hidden',
            show: () => { viewPrefs.outline = true; saveViewPrefs(); delete surface.dataset.ddnOutline; }, hide: () => { viewPrefs.outline = false; saveViewPrefs(); surface.dataset.ddnOutline = 'hidden'; },
            detaching: () => { surface.dataset.ddnOutline = 'hidden'; }, returned: () => {
                if (viewPrefs.outline !== false)
                    delete surface.dataset.ddnOutline;
            }, available: () => !!viewer },
    ];
    const panelOf = (id) => windowPanels.find(item => item.id === id);
    const panelMode = (definition) => {
        const drawer = (0, drawer_js_1.drawerFor)(viewerContainer(), definition.id);
        if (drawer)
            return drawer.mode;
        const detached = detachedPanels.get(definition.id);
        return detached ? (detached.kind === 'window' ? 'popout' : 'floating') : definition.shown() ? 'docked' : 'hidden';
    };
    function setPanelMode(definition, mode) {
        if (definition.id !== 'source') {
            if (!(0, drawer_js_1.drawerFor)(viewerContainer(), definition.id) && mode !== 'hidden')
                definition.show();
            const drawer = (0, drawer_js_1.drawerFor)(viewerContainer(), definition.id);
            if (drawer) {
                drawer.setMode(mode);
                refreshMenus();
                return;
            }
        }
        detachedPanels.get(definition.id)?.dock();
        if (mode === 'hidden') {
            definition.hide();
            refreshMenus();
            return;
        }
        if (!definition.shown())
            definition.show();
        const element = definition.element();
        if (mode === 'docked' || !element) {
            refreshMenus();
            return;
        }
        definition.detaching?.();
        const options = { title: definition.title, name: definition.id, hostClass: definition.hostClass ?? '', onKeydown: globalKeydown, onReturn: () => { detachedPanels.delete(definition.id); definition.returned?.(); refreshSourcePanelControls(); refreshMenus(); } };
        let result = mode === 'popout' ? (0, popout_js_1.popOut)(element, options) : undefined;
        if (mode === 'popout' && !result)
            toast('The browser blocked the new window, so the panel floats in the page instead. Allow pop-ups for this page to use a second monitor.', 'error');
        result ??= (0, popout_js_1.floatPanel)(element, { ...options, actions: [{ label: 'Dock', title: 'Return the panel to its place', run: () => setPanelMode(definition, 'docked') }, { label: 'Pop out', title: 'Open in its own window, for example on a second monitor', run: () => setPanelMode(definition, 'popout') }] });
        detachedPanels.set(definition.id, result);
        refreshSourcePanelControls();
        refreshMenus();
    }
    const sourceModes = doc.createElement('div');
    sourceModes.className = 'ddn-drawer-controls';
    sourceModes.setAttribute('role', 'group');
    sourceModes.setAttribute('aria-label', 'Source panel controls');
    sourceHeading.insertBefore(sourceModes, collapseSource);
    const sourceModeButtons = new Map();
    for (const [mode, label, icon, hint] of [['floating', 'Float source', 'layers', 'Float the source panel over the page.'], ['popout', 'Pop out source', 'expand', 'Open the source in its own window; move that window to another monitor.'], ['docked', 'Dock source', 'fit', 'Return the source to its drawer.']]) {
        const button = doc.createElement('button');
        button.type = 'button';
        button.setAttribute('aria-label', label);
        button.title = hint;
        button.append((0, ui_icons_js_1.uiIcon)(doc, icon));
        button.addEventListener('click', () => setPanelMode(panelOf('source'), mode));
        sourceModes.append(button);
        sourceModeButtons.set(mode, button);
    }
    function refreshSourcePanelControls() {
        for (const [mode, button] of sourceModeButtons)
            button.hidden = mode === panelMode(panelOf('source'));
    }
    refreshSourcePanelControls();
    surface.addEventListener('ddn:drawer-change', event => {
        const detail = event.detail;
        if (!detail?.drawer || event.target !== viewerContainer())
            return;
        const { id, drawer } = detail;
        if (drawer.detached)
            detachedPanels.set(id, drawer.detached);
        else
            detachedPanels.delete(id);
        if (id === 'navigator') {
            viewPrefs.outline = drawer.mode !== 'hidden';
            saveViewPrefs();
            if (drawer.mode === 'docked')
                delete surface.dataset.ddnOutline;
            else
                surface.dataset.ddnOutline = 'hidden';
        }
        refreshMenus();
    });
    const togglePanel = (id) => {
        const definition = panelOf(id);
        if (panelMode(definition) === 'hidden') {
            if (!definition.available || definition.available())
                setPanelMode(definition, 'docked');
        }
        else
            setPanelMode(definition, 'hidden');
    };
    const panelMenu = (id, shortcut) => {
        const definition = panelOf(id), usable = () => panelMode(definition) !== 'hidden' || !definition.available || definition.available();
        const mode = (label, value) => ({ label, radio: true, checked: () => panelMode(definition) === value, enabled: usable, ...(definition.hint ? { hint: definition.hint } : {}), run: () => setPanelMode(definition, value) });
        return { kind: 'submenu', label: definition.title, items: () => [mode('Docked', 'docked'), mode('Floating', 'floating'), mode('Pop out to a window', 'popout'), { ...mode('Hidden', 'hidden'), ...(shortcut ? { shortcut } : {}) }] };
    };
    const toggleSource = () => { const definition = panelOf('source'), current = panelMode(definition); setPanelMode(definition, current === 'hidden' ? 'docked' : current === 'docked' ? 'hidden' : 'docked'); };
    const runFind = () => {
        if (panelMode(panelOf('navigator')) === 'hidden')
            setPanelMode(panelOf('navigator'), 'docked');
        return runCommand('edit.find');
    };
    const zoomPresets = [25, 50, 75, 100, 150, 200, 400];
    const recentItems = () => { const list = readRecent(); return list.length ? list.map(item => ({ label: item.title, run: () => openRecent(item) })) : [{ label: 'No recent documents in this browser', enabled: () => false }]; };
    const menuSpecs = [
        { label: 'File', items: () => isVerifier ? [
                { label: 'Open files…', shortcut: 'Ctrl+O', run: openFiles }, { label: 'Open a sample…', run: openSampleDialog }, separator,
                heading('Report'), { label: 'Download report', run: downloadSource }, separator, { label: 'Keyboard shortcuts', shortcut: '?', run: showShortcuts },
            ] : [
                ...(isDesigner ? [{ label: 'New diagram…', shortcut: 'Ctrl+Alt+N', run: newDocument }, weaver('New from template…')] : []),
                { label: 'Open files…', shortcut: 'Ctrl+O', run: openFiles }, { label: 'Open a sample…', run: openSampleDialog },
                ...(isDesigner ? [{ kind: 'submenu', label: 'Open recent', items: recentItems }] : []),
                separator, heading('Save'),
                { label: 'Download .ddn', shortcut: 'Ctrl+S', run: downloadSource },
                { label: 'Save as bundle (.zip)', shortcut: 'Ctrl+Shift+S', run: saveBundle },
                { label: 'Download assets', run: downloadAssets },
                ...(isDesigner ? [weaver('Save as template…'), { label: 'Revert to last opened', enabled: () => !!lastOpened, hint: 'Nothing has been opened yet', run: revert }] : []),
                separator, heading('Import'),
                needsDesigner(bus('CSV as dataset…', 'workarea.import-csv')), needsDesigner({ label: 'CSS stylesheet…', run: importStylesheet, enabled: () => !!viewer }),
                separator, heading('Export'),
                { label: 'Export SVG', run: exportAs('svg') }, { label: 'Export PNG', run: exportAs('png') }, { label: 'Export JSON', run: exportAs('json') }, { label: 'Export Markdown', run: exportAs('markdown') }, { label: 'Export CSV', run: exportAs('csv') },
                { label: 'Print…', shortcut: 'Ctrl+P', run: printCurrent, enabled: () => !!viewer },
            ] },
        { label: 'Edit', items: () => [
                bus('Undo', 'edit.undo', { shortcut: 'Ctrl+Z' }), bus('Redo', 'edit.redo', { shortcut: 'Ctrl+Shift+Z' }), separator,
                bus('Cut', 'edit.cut', { shortcut: 'Ctrl+X', hint: 'Select an element first' }), bus('Copy', 'edit.copy', { shortcut: 'Ctrl+C', hint: 'Select an element first' }),
                bus('Paste', 'edit.paste', { shortcut: 'Ctrl+V' }), bus('Paste in place', 'edit.paste-in-place', { shortcut: 'Ctrl+Shift+V' }), bus('Paste as reference', 'edit.paste-reference', { shortcut: 'Ctrl+Alt+V' }),
                bus('Duplicate', 'edit.duplicate', { shortcut: 'Ctrl+D', hint: 'Select an element first' }), bus('Delete', 'edit.delete', { shortcut: 'Delete', hint: 'Select an element first' }), separator,
                later('Select all in view', 'Ctrl+A'), later('Select connected'), bus('Deselect', 'edit.deselect', { shortcut: 'Esc' }), separator,
                { label: 'Find…', shortcut: 'Ctrl+F', enabled: () => (0, ui_commands_js_1.commandEnabled)(command('edit.find')), run: () => { runFind(); } },
                bus('Rename', 'edit.rename', { shortcut: 'F2', hint: 'Select an element first' }), bus('Properties', 'edit.properties', { shortcut: 'P', hint: 'Select an element first' }),
                bus('Appearance & presets…', 'edit.appearance', { hint: 'Select an element first' }), bus('Review status…', 'edit.status', { hint: 'Select an element first' }),
            ] },
        { label: 'WorkArea', items: () => documentItems([
                bus('Workarea settings…', 'workarea.settings', { hint: 'Open a document in the designer first' }), separator, heading('Views and elements'),
                bus('Add view…', 'workarea.add-view'), { label: 'Add document view…', enabled: () => (0, ui_commands_js_1.commandEnabled)(command('document.new')), hint: 'Open a document in the designer first', run: () => { runCommand('document.new'); } },
                later('Place an existing view'), bus('Add element…', 'workarea.add-element', { shortcut: 'A' }), bus('Add existing element…', 'workarea.add-existing'), bus('Connect', 'workarea.connect', { shortcut: 'C' }), bus('Add entity', 'workarea.add-entity', { hint: 'ERD views only' }),
                bus('Reflow view', 'workarea.reflow', { hint: 'Release fixed positions and arrange the active diagram' }),
                { label: 'Navigator', shortcut: 'Ctrl+Shift+E', checked: () => panelMode(panelOf('navigator')) !== 'hidden', run: () => togglePanel('navigator') },
                later('Layers'), later('Regions'), later('Bookmarks'), separator, heading('Data'),
                bus('Data sources and datasets…', 'workarea.datasets'), bus('Import CSV as dataset…', 'workarea.import-csv'), bus('Projection settings…', 'workarea.projection', { hint: 'Data-bound views only' }),
                separator, heading('Styles'), later('Workarea defaults…'), needsDesigner({ label: 'Import stylesheet…', run: importStylesheet, enabled: () => !!viewer }),
                separator, weaver('Managed connectors…'), weaver('Collaborators and presence'),
            ]).map(needsDesigner) },
        { label: 'View', items: () => documentItems([
                bus('Zoom in', 'view.zoom-in', { shortcut: 'Ctrl+=' }), bus('Zoom out', 'view.zoom-out', { shortcut: 'Ctrl+−' }),
                { kind: 'submenu', label: 'Zoom to', enabled: () => (0, ui_commands_js_1.commandEnabled)(command('view.zoom')), items: () => zoomPresets.map(percent => bus(percent + ' %', 'view.zoom', { argument: percent, checked: () => command('view.zoom')?.value?.() === percent + '%', radio: true })) },
                bus('Actual size (100 %)', 'view.actual-size', { shortcut: 'Ctrl+0' }), separator,
                bus('Fit workarea', 'view.fit-workarea', { shortcut: 'Shift+1' }), bus('Fit selection', 'view.fit-selection', { shortcut: 'Shift+2' }), bus('Fit current view', 'view.fit-view', { shortcut: 'Shift+3' }),
                bus('Expand view', 'view.expand', { checked: () => !!command('view.expand')?.checked?.() }), bus('Back', 'view.back', { shortcut: 'Alt+←' }), bus('Forward', 'view.forward', { shortcut: 'Alt+→' }),
                bus('Item details…', 'view.details'), separator,
                setting('Show grid', () => !!viewPrefs.grid, () => toggleSetting('grid')), setting('Snap to grid', () => !!viewPrefs.snap, () => toggleSetting('snap')),
                later('Rulers'), later('Guides'),
                { kind: 'submenu', label: 'Mini-views when small', items: () => [choice('Automatic', () => viewPrefs.lod ?? 'auto', 'auto', value => { viewPrefs.lod = value; saveViewPrefs(); applyViewSettings(); }), choice('Always frames', () => viewPrefs.lod ?? 'auto', 'frames', value => { viewPrefs.lod = value; saveViewPrefs(); applyViewSettings(); }), choice('Never', () => viewPrefs.lod ?? 'auto', 'full', value => { viewPrefs.lod = value; saveViewPrefs(); applyViewSettings(); })] },
                { kind: 'submenu', label: 'Mouse wheel', items: () => [choice('Scrolls (Ctrl+wheel zooms)', () => surface.dataset.ddnWheel ?? 'zoom', 'pan', value => { viewPrefs.wheel = value; saveViewPrefs(); applyViewSettings(false); }), choice('Zooms', () => surface.dataset.ddnWheel ?? 'zoom', 'zoom', value => { viewPrefs.wheel = value; saveViewPrefs(); applyViewSettings(false); })] },
                later('Show documents at print size'), separator,
                ...(isDesigner ? [setting('Quick-access toolbar', () => viewPrefs.quick !== false, () => showSetting('quick'))] : []),
                setting('Status bar', () => viewPrefs.status !== false, () => showSetting('status')),
                { kind: 'submenu', label: 'Interface theme', items: () => [...ui_theme_js_1.UI_THEME_NAMES.map(name => choice(name.charAt(0).toUpperCase() + name.slice(1), () => interfaceTheme, name, value => setTheme(value))), separator, { label: 'Interface colours…', run: () => customise.click() }] },
                setting('Reduced motion', () => !!viewPrefs.motion, () => toggleSetting('motion')), setting('High contrast', () => !!viewPrefs.contrast, () => toggleSetting('contrast')),
                { label: 'Full screen', shortcut: 'F11', run: toggleFullScreen, checked: () => !!doc.fullscreenElement },
            ]) },
        { label: 'Document', items: () => documentItems([
                bus('New document view…', 'document.new', { hint: 'Open a document in the designer first' }),
                weaver('PPTX output'), weaver('Send by email…'), separator,
                bus('Page setup…', 'document.page-setup'), bus('Header…', 'document.header'), bus('Footer…', 'document.footer'),
                { label: 'Capture scope…', run: chooseCaptureScope, enabled: () => !!viewer }, later('Page preview'), later('Document defaults and stylesheet…'), separator,
                bus('Export document…', 'document.export', { shortcut: 'Ctrl+E' }), { label: 'Print…', shortcut: 'Ctrl+P', run: printCurrent, enabled: () => !!viewer },
            ]).map(needsDesigner) },
        { label: 'Window', items: () => [
                panelMenu('source', 'Ctrl+\\'), panelMenu('inspector', 'Ctrl+I'), panelMenu('palette'), panelMenu('navigator', 'Ctrl+Shift+E'), separator,
                heading('Open windows'),
                ...(detachedPanels.size ? [...detachedPanels].map(([id, detached]) => ({ label: panelOf(id).title + (detached.kind === 'window' ? ' (window)' : ' (floating)'), run: () => detached.focus() })) : [{ label: 'No detached panels', enabled: () => false }]),
                separator, { label: 'Dock all', enabled: () => detachedPanels.size > 0, run: () => {
                        for (const detached of [...detachedPanels.values()])
                            detached.dock();
                    } },
                { label: 'Reset layout', run: () => {
                        for (const detached of [...detachedPanels.values()])
                            detached.dock();
                        try {
                            for (const key of Object.keys(localStorage))
                                if (key.startsWith('ddn.detached.'))
                                    localStorage.removeItem(key);
                        }
                        catch { }
                        delete viewPrefs.sourceWidth;
                        viewPrefs.sourceHidden = false;
                        viewPrefs.outline = true;
                        saveViewPrefs();
                        setSourceWidth(340, false);
                        showSource(false);
                        applyViewSettings();
                        toast('Layout reset');
                    } },
            ] },
        { label: 'Help', items: () => [
                { label: 'Command search…', shortcut: 'Ctrl+K', run: commandSearch }, { label: 'Keyboard shortcuts', shortcut: '?', run: showShortcuts }, separator,
                help('Guide', 'guide/index.html', 'F1'), help('Language reference', 'reference/index.html'), help('Field guide', 'field-guide/index.html'), help('Gallery', 'gallery/index.html'), separator,
                { label: "What's new", run: showWhatsNew }, { label: 'About DDN', run: showAbout },
            ] },
    ];
    const menuBar = (0, menus_js_1.createMenuBar)(doc, menuSpecs, { label: isDesigner ? 'Designer menu' : isVerifier ? 'Verifier menu' : 'Viewer menu', onError: showError });
    bar.insertBefore(menuBar.element, siteSlot);
    let menuFrame = 0;
    refreshMenus = () => {
        if (menuFrame || !menuBar.isOpen())
            return;
        menuFrame = requestAnimationFrame(() => { menuFrame = 0; menuBar.refresh(); });
    };
    const zoomGroup = doc.createElement('div');
    zoomGroup.className = 'app-zoom';
    zoomGroup.setAttribute('role', 'group');
    zoomGroup.setAttribute('aria-label', 'Zoom');
    zoomGroup.hidden = true;
    const zoomButton = (text, label, title, run) => { const button = doc.createElement('button'); button.type = 'button'; button.textContent = text; button.setAttribute('aria-label', label); button.title = title; button.addEventListener('click', run); zoomGroup.append(button); return button; };
    const zoomOutButton = zoomButton('−', 'Zoom out', 'Zoom out (Ctrl+−)', () => { runCommand('view.zoom-out'); });
    const zoomValue = zoomButton('100%', 'Zoom level', 'Choose a zoom level', () => (0, menus_js_1.openPopupMenu)(zoomValue, documentItems([
        ...zoomPresets.map(percent => ({ label: percent + ' %', radio: true, checked: () => command('view.zoom')?.value?.() === percent + '%', run: () => { runCommand('view.zoom', percent); } })),
        separator, { label: 'Fit workarea', shortcut: 'Shift+1', run: () => { runCommand('view.fit-workarea'); } }, { label: 'Fit selection', shortcut: 'Shift+2', enabled: () => (0, ui_commands_js_1.commandEnabled)(command('view.fit-selection')), run: () => { runCommand('view.fit-selection'); } }, { label: 'Fit current view', shortcut: 'Shift+3', enabled: () => (0, ui_commands_js_1.commandEnabled)(command('view.fit-view')), run: () => { runCommand('view.fit-view'); } },
        separator, { label: 'Custom…', run: customZoom },
    ]), 'Zoom level', showError));
    zoomValue.className = 'app-zoom-value';
    zoomValue.setAttribute('aria-haspopup', 'menu');
    zoomValue.setAttribute('aria-expanded', 'false');
    const zoomInButton = zoomButton('+', 'Zoom in', 'Zoom in (Ctrl+=)', () => { runCommand('view.zoom-in'); });
    function customZoom() {
        const original = parseInt(command('view.zoom')?.value?.() ?? '100', 10);
        const dialog = (0, dialogs_js_1.createStandardDialog)(doc.body, { title: 'Zoom level', modal: false });
        const field = (0, dialogs_js_1.numberField)(dialog.body, 'Zoom (%)', original, { min: 5, max: 3200 });
        field.addEventListener('input', () => {
            if (!field.checkValidity() || !Number.isFinite(field.valueAsNumber)) {
                dialog.showError('Enter a zoom from 5 % to 3200 %.');
                return;
            }
            dialog.showError('');
            runCommand('view.zoom', field.valueAsNumber);
        });
    }
    status.append(zoomGroup);
    const updateStatusZoom = () => {
        const zoom = command('view.zoom');
        zoomGroup.hidden = !zoom;
        if (!zoom)
            return;
        zoomValue.textContent = zoom.value?.() ?? '—';
        const enabled = (0, ui_commands_js_1.commandEnabled)(zoom);
        zoomOutButton.disabled = zoomInButton.disabled = zoomValue.disabled = !enabled;
    };
    surface.addEventListener(ui_commands_js_1.UI_COMMANDS_CHANGED, () => { updateStatusZoom(); refreshMenus(); });
    const updateToolsRow = () => { tools.dataset.empty = String(![...tools.children].some(child => child instanceof HTMLElement && !child.hidden && child.tagName !== 'INPUT' && !child.classList.contains('app-spacer') && getComputedStyle(child).display !== 'none')); };
    new MutationObserver(updateToolsRow).observe(tools, { subtree: true, attributes: true, attributeFilter: ['hidden'], childList: true });
    updateToolsRow();
    function globalKeydown(event) {
        if (event.defaultPrevented)
            return;
        const target = event.target;
        const within = (selector) => !!target && typeof target.closest === 'function' && !!target.closest(selector);
        const typing = !!target?.isContentEditable || within('input, textarea, select, [contenteditable=true]');
        const inDiagram = within('.ddn-viewer') && target.ownerDocument === doc, inDialog = within('.ddn-ui-dialog');
        const mod = event.ctrlKey || event.metaKey, letter = event.code.startsWith('Key') ? event.code.slice(3).toLowerCase() : event.key.toLowerCase();
        const take = (done) => {
            if (done)
                event.preventDefault();
        };
        if (mod && !event.altKey && letter === 's') {
            event.preventDefault();
            void (event.shiftKey ? saveBundle() : downloadSource()).catch(showError);
            return;
        }
        if (mod && !event.altKey && !event.shiftKey && letter === 'o') {
            event.preventDefault();
            void openFiles().catch(showError);
            return;
        }
        if (mod && event.key === '\\') {
            event.preventDefault();
            toggleSource();
            return;
        }
        if (mod && !event.altKey && !event.shiftKey && letter === 'k') {
            event.preventDefault();
            if (!doc.querySelector('.ddn-ui-dialog[aria-modal=true]'))
                commandSearch();
            return;
        }
        if (event.key === 'F1') {
            event.preventDefault();
            openHelp();
            return;
        }
        if (mod && event.altKey && letter === 'n' && isDesigner) {
            event.preventDefault();
            void newDocument().catch(showError);
            return;
        }
        if (typing || inDialog || menuBar.isOpen())
            return;
        if (event.key === '?' && !mod && !doc.querySelector('.ddn-ui-dialog')) {
            event.preventDefault();
            showShortcuts();
            return;
        }
        if (mod && event.shiftKey && !event.altKey && letter === 'e') {
            event.preventDefault();
            togglePanel('navigator');
            return;
        }
        if (mod && !event.shiftKey && !event.altKey && letter === 'i') {
            if (isDesigner) {
                event.preventDefault();
                togglePanel('inspector');
            }
            return;
        }
        if (mod && !event.shiftKey && !event.altKey && letter === 'e') {
            take(runCommand('document.export'));
            return;
        }
        if (mod && !event.shiftKey && !event.altKey && letter === 'p') {
            event.preventDefault();
            void printCurrent().catch(showError);
            return;
        }
        if (mod && !event.shiftKey && !event.altKey && letter === 'f') {
            take(runFind());
            return;
        }
        if (mod && !event.altKey && (event.key === '=' || event.key === '+')) {
            take(runCommand('view.zoom-in'));
            return;
        }
        if (mod && !event.altKey && (event.key === '-' || event.key === '_')) {
            take(runCommand('view.zoom-out'));
            return;
        }
        if (mod && !event.altKey && event.key === '0') {
            take(runCommand('view.actual-size'));
            return;
        }
        if (event.altKey && !mod && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
            take(runCommand(event.key === 'ArrowLeft' ? 'view.back' : 'view.forward'));
            return;
        }
        if (event.shiftKey && !mod && !event.altKey && ['Digit1', 'Digit2', 'Digit3'].includes(event.code)) {
            take(runCommand(event.code === 'Digit1' ? 'view.fit-workarea' : event.code === 'Digit2' ? 'view.fit-selection' : 'view.fit-view'));
            return;
        }
        if (!isDesigner)
            return;
        if (mod && !event.altKey && !event.shiftKey && letter === 'x') {
            take(runCommand('edit.cut'));
            return;
        }
        if (mod && !event.altKey && !event.shiftKey && letter === 'c') {
            take(runCommand('edit.copy'));
            return;
        }
        if (mod && event.altKey && letter === 'v') {
            take(runCommand('edit.paste-reference'));
            return;
        }
        if (mod && event.shiftKey && letter === 'v') {
            take(runCommand('edit.paste-in-place'));
            return;
        }
        if (mod && !event.altKey && letter === 'v') {
            take(runCommand('edit.paste'));
            return;
        }
        if (mod && !event.shiftKey && !event.altKey && letter === 'd') {
            take(runCommand('edit.duplicate'));
            return;
        }
        if (mod && !event.shiftKey && !event.altKey && letter === 'y') {
            take(runCommand('edit.redo'));
            return;
        }
        if (!inDiagram && mod && !event.altKey && letter === 'z') {
            take(runCommand(event.shiftKey ? 'edit.redo' : 'edit.undo'));
            return;
        }
    }
    doc.addEventListener('keydown', globalKeydown);
    applyViewSettings(false);
    surface.addEventListener('dragover', event => event.preventDefault());
    surface.addEventListener('drop', event => {
        event.preventDefault();
        if (event.dataTransfer?.files)
            void (async () => {
                const selected = Array.from(event.dataTransfer.files);
                if (await confirmReplace())
                    await readFiles(selected);
            })().catch(showError);
    });
    const draft = pendingRecovery;
    if (factories.initial) {
        entry = documentEntry = factories.initial.sources.entry;
        for (const file of factories.initial.sources.files)
            files.set(file.id, file);
        for (const [id, asset] of Object.entries(factories.initial.assets ?? {})) {
            assets.set(id, new File([asset.text], id, { type: asset.mime }));
            draftAssets.push((0, document_draft_js_1.encodeDraftAsset)(id, asset.mime, new TextEncoder().encode(asset.text)));
        }
        editor.value = files.get(entry)?.text ?? '';
    }
    else {
        editor.value = isDesigner ? BLANK_DOCUMENT : examples['ERD whiteboard'];
        files.set(entry, { id: entry, text: editor.value, revision: String(++sequence), encoding: 'utf-8', writable: true });
    }
    refreshFiles();
    markClean();
    void open().then(() => {
        factories.ready?.({ ...(viewer ? { viewer } : {}), ...(designer ? { designer } : {}), ...(verifier ? { verifier } : {}) });
        if (draft) {
            const banner = doc.createElement('div');
            recoveryBanner = banner;
            banner.className = 'app-banner';
            banner.setAttribute('role', 'region');
            banner.setAttribute('aria-label', 'Unsaved work found');
            const when = new Date(draft.savedAt);
            const text = doc.createElement('span');
            text.textContent = `You have unsaved work from ${Number.isNaN(when.getTime()) ? 'an earlier visit' : when.toLocaleString()} (${draft.files.length} file${draft.files.length === 1 ? '' : 's'}).`;
            const sp = doc.createElement('span');
            sp.className = 'app-spacer';
            const restore = doc.createElement('button');
            restore.type = 'button';
            restore.textContent = 'Restore';
            restore.classList.add('app-primary');
            const discard = doc.createElement('button');
            discard.type = 'button';
            discard.textContent = 'Discard';
            banner.append(text, sp, restore, discard);
            main.prepend(banner);
            restore.addEventListener('click', () => {
                void (async () => {
                    if (!await confirmReplace(false))
                        return;
                    if (!await loadSources(draft, (0, document_draft_js_1.restoreDraftAssets)(draft)))
                        return;
                    const operation = openGeneration + 1;
                    try {
                        await open(true);
                    }
                    finally {
                        if (operation === openGeneration) {
                            setDirty(true);
                            persistDraft();
                        }
                    }
                    if (operation !== openGeneration)
                        return;
                    toast('Restored your unsaved work');
                })().catch(showError);
            });
            discard.addEventListener('click', () => clearRecovery());
        }
    }).catch(showError);
}

},
"standalone/src/website-navigation.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.installWebsiteNavigation = installWebsiteNavigation;
const ui_icons_js_1 = require("viewer/src/ui-icons.js");
function installWebsiteNavigation(mode) {
    const parameters = new URLSearchParams(location.search);
    const links = document.createElement('nav');
    links.className = 'app-site-nav';
    links.setAttribute('aria-label', 'Website and utilities');
    const siteLinks = document.createElement('div'), modeLinks = document.createElement('div');
    siteLinks.className = 'app-site-links';
    modeLinks.className = 'app-site-links app-mode-links';
    links.append(siteLinks, modeLinks);
    const navigationStyle = document.createElement('style');
    navigationStyle.textContent = `.app-site-nav{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font:12px Inter,system-ui,sans-serif;min-width:0}.app-site-nav .app-mode-links{border:1px solid var(--ddn-ui-border);border-radius:9px;padding:2px;background:color-mix(in srgb,var(--ddn-ui-bg) 70%,transparent)}.app-site-nav .app-mode-links a{padding:4px 8px}@media(max-width:1050px){.app-site-nav .app-site-links:not(.app-mode-links) a span{display:none}}@media(max-width:750px){.app-site-nav{width:100%;justify-content:space-between}}`;
    document.head.append(navigationStyle);
    const navigation = [];
    for (const [title, path, icon] of [['DDN home', '../index.html', 'layers'], ['Gallery', '../gallery/index.html', 'grid'], ['Guide', '../guide/index.html', 'info'], ['Viewer', 'view', 'eye'], ['Designer', 'design', 'pen'], ['Verifier', 'verify', 'check']]) {
        const link = document.createElement('a');
        const text = document.createElement('span');
        text.textContent = title;
        link.append((0, ui_icons_js_1.uiIcon)(document, icon), text);
        link.title = path.includes('.html') ? title : `Switch to the ${title.toLowerCase()}`;
        if ((mode === 'designer' && title === 'Designer') || (mode === 'verifier' && title === 'Verifier') || (mode === 'viewer' && title === 'Viewer'))
            link.setAttribute('aria-current', 'page');
        (path.includes('.html') ? siteLinks : modeLinks).append(link);
        navigation.push({ link, path: path });
    }
    const refreshNavigation = () => {
        const theme = document.body.dataset.ddnUiTheme ?? 'dark';
        for (const { link, path } of navigation) {
            if (path.includes('.html'))
                link.href = path + '?theme=' + encodeURIComponent(theme);
            else {
                const query = new URLSearchParams(parameters);
                query.set('mode', path);
                query.set('theme', theme);
                link.href = './index.html?' + query;
            }
        }
    };
    refreshNavigation();
    document.addEventListener('ddn:interface-theme', refreshNavigation);
    const slot = document.querySelector('.app-site-slot');
    if (slot)
        slot.append(links);
    else
        document.body.prepend(links);
    if (parameters.get('embed') === '1') {
        links.style.display = 'none';
        const style = document.createElement('style');
        style.textContent = '.app-source,.app-tools,.app-bar,nav[aria-label="Website and utilities"],.app-status{display:none}.app-main{display:block;flex:none;height:100dvh;min-height:300px;padding:0}.app-surface{height:100%;border:0;border-radius:0;box-shadow:none}';
        document.head.append(style);
    }
}

},
"standalone/src/zip.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.zipFiles = zipFiles;
const table = (() => {
    const values = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
        let c = n;
        for (let k = 0; k < 8; k++)
            c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
        values[n] = c >>> 0;
    }
    return values;
})();
function crc32(bytes) {
    let crc = 0xffffffff;
    for (const byte of bytes)
        crc = table[(crc ^ byte) & 0xff] ^ (crc >>> 8);
    return (crc ^ 0xffffffff) >>> 0;
}
function zipFiles(entries, date = new Date()) {
    const encoder = new TextEncoder(), parts = [], central = [];
    const time = (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2);
    const day = ((Math.max(1980, date.getFullYear()) - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate();
    let offset = 0;
    const names = new Set();
    for (const entry of entries) {
        const name = entry.name.replace(/^\/+/, '').replace(/\\/g, '/');
        if (!name || name.split('/').includes('..') || names.has(name))
            throw Error('Invalid or duplicate bundle entry: ' + entry.name);
        names.add(name);
        const nameBytes = encoder.encode(name), crc = crc32(entry.bytes), size = entry.bytes.length;
        const local = new Uint8Array(30 + nameBytes.length), view = new DataView(local.buffer);
        view.setUint32(0, 0x04034b50, true);
        view.setUint16(4, 20, true);
        view.setUint16(6, 0x0800, true);
        view.setUint16(8, 0, true);
        view.setUint16(10, time, true);
        view.setUint16(12, day, true);
        view.setUint32(14, crc, true);
        view.setUint32(18, size, true);
        view.setUint32(22, size, true);
        view.setUint16(26, nameBytes.length, true);
        view.setUint16(28, 0, true);
        local.set(nameBytes, 30);
        const header = new Uint8Array(46 + nameBytes.length), cv = new DataView(header.buffer);
        cv.setUint32(0, 0x02014b50, true);
        cv.setUint16(4, 20, true);
        cv.setUint16(6, 20, true);
        cv.setUint16(8, 0x0800, true);
        cv.setUint16(10, 0, true);
        cv.setUint16(12, time, true);
        cv.setUint16(14, day, true);
        cv.setUint32(16, crc, true);
        cv.setUint32(20, size, true);
        cv.setUint32(24, size, true);
        cv.setUint16(28, nameBytes.length, true);
        cv.setUint32(42, offset, true);
        header.set(nameBytes, 46);
        parts.push(local, entry.bytes);
        central.push(header);
        offset += local.length + size;
    }
    const centralSize = central.reduce((sum, part) => sum + part.length, 0);
    const end = new Uint8Array(22), ev = new DataView(end.buffer);
    ev.setUint32(0, 0x06054b50, true);
    ev.setUint16(8, entries.length, true);
    ev.setUint16(10, entries.length, true);
    ev.setUint32(12, centralSize, true);
    ev.setUint32(16, offset, true);
    return new Blob([...parts, ...central, end].map(part => part.slice().buffer), { type: 'application/zip' });
}

}});})();
