# Audion Build Licenses Scan Report

- Project: **Audion Address Processor** (`audion-address-processor`)
- Run: `20261015T231850Z_audion-address-processor_4cdebd1a`
- Scan root (from the project root): `.`
- Output (from the project root): `licenses`
- Status: **REVIEW**
- Components: 113
- Bundled: 113
- Optional runtime: 0

## Issues

| Severity | Code | Component/path | Message |
|---|---|---|---|
| REVIEW | `COPYLEFT_LINKED_INTO_PROGRAM` | pymupdf | pymupdf is under GPL-3.0 and runs inside the program (python_import). The program as a whole is then distributed under the GPL: its complete source has to be offered. Decide whether that is intended, or run the component as a separate program. The licence of pymupdf was made out from a descriptive line ("Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License"), not from an exact expression: check what the installed files are really under, and state it in a profile. |

## Changes since previous scan

| Component | Change | Old | New |
|---|---|---:|---:|
| Audion launcher | `UNCHANGED` | bundled | bundled |
| Avalonia | `UNCHANGED` | 12.1.3 | 12.1.3 |
| Avalonia.Angle.Windows.Natives | `UNCHANGED` | 2.1.27548.20260419 | 2.1.27548.20260419 |
| Avalonia.Desktop | `UNCHANGED` | 12.1.3 | 12.1.3 |
| Avalonia.Fonts.Inter | `UNCHANGED` | 12.1.3 | 12.1.3 |
| Avalonia.FreeDesktop | `UNCHANGED` | 12.1.3 | 12.1.3 |
| Avalonia.FreeDesktop.AtSpi | `UNCHANGED` | 12.1.3 | 12.1.3 |
| Avalonia.HarfBuzz | `UNCHANGED` | 12.1.3 | 12.1.3 |
| Avalonia.Native | `UNCHANGED` | 12.1.3 | 12.1.3 |
| Avalonia.Remote.Protocol | `UNCHANGED` | 12.1.3 | 12.1.3 |
| Avalonia.Skia | `UNCHANGED` | 12.1.3 | 12.1.3 |
| Avalonia.Themes.Fluent | `UNCHANGED` | 12.1.3 | 12.1.3 |
| Avalonia.Win32 | `UNCHANGED` | 12.1.3 | 12.1.3 |
| Avalonia.X11 | `UNCHANGED` | 12.1.3 | 12.1.3 |
| colorama | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 0.4.6 | 0.4.6 |
| DAWG2-Python | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 0.9.0 | 0.9.0 |
| et_xmlfile | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 2.0.0 | 2.0.0 |
| HarfBuzzSharp | `UNCHANGED` | 8.3.1.3 | 8.3.1.3 |
| HarfBuzzSharp.NativeAssets.Win32 | `UNCHANGED` | 8.3.1.3 | 8.3.1.3 |
| Humanizer.Core | `UNCHANGED` | 2.14.1 | 2.14.1 |
| iniconfig | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 2.3.1 | 2.3.1 |
| Inter | `UNCHANGED` | 3.019 | 3.019 |
| JetBrains Mono | `UNCHANGED` | 2.211 | 2.211 |
| Json.More.Net | `UNCHANGED` | 2.1.1 | 2.1.1 |
| JsonPointer.Net | `UNCHANGED` | 5.3.1 | 5.3.1 |
| JsonSchema.Net | `UNCHANGED` | 7.4.0 | 7.4.0 |
| Lucide | `UNCHANGED` | 1.48.0 | 1.48.0 |
| Markdig.Signed | `UNCHANGED` | 0.44.0 | 0.44.0 |
| MicroCom.Runtime | `UNCHANGED` | 0.11.6 | 0.11.6 |
| Microsoft.ApplicationInsights | `UNCHANGED` | 2.23.0 | 2.23.0 |
| Microsoft.Bcl.AsyncInterfaces | `UNCHANGED` | 10.0.5 | 10.0.5 |
| Microsoft.CodeAnalysis.Common | `UNCHANGED` | 5.0.0 | 5.0.0 |
| Microsoft.CodeAnalysis.CSharp | `UNCHANGED` | 5.0.0 | 5.0.0 |
| Microsoft.Extensions.ObjectPool | `UNCHANGED` | 10.0.5 | 10.0.5 |
| Microsoft.Management.Infrastructure | `UNCHANGED` | 3.0.0 | 3.0.0 |
| Microsoft.Management.Infrastructure.CimCmdlets | `UNCHANGED` | 7.6.6 | 7.6.6 |
| Microsoft.Management.Infrastructure.Runtime.Win | `UNCHANGED` | 3.0.0 | 3.0.0 |
| Microsoft.NETCore.App.Runtime.win-x64 | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 10.0.12 | 10.0.13 |
| Microsoft.PowerShell.Commands.Diagnostics | `UNCHANGED` | 7.6.6 | 7.6.6 |
| Microsoft.PowerShell.Commands.Management | `UNCHANGED` | 7.6.6 | 7.6.6 |
| Microsoft.PowerShell.Commands.Utility | `UNCHANGED` | 7.6.6 | 7.6.6 |
| Microsoft.PowerShell.ConsoleHost | `UNCHANGED` | 7.6.6 | 7.6.6 |
| Microsoft.PowerShell.CoreCLR.Eventing | `UNCHANGED` | 7.6.6 | 7.6.6 |
| Microsoft.PowerShell.MarkdownRender | `UNCHANGED` | 7.2.1 | 7.2.1 |
| Microsoft.PowerShell.Native | `UNCHANGED` | 700.0.0 | 700.0.0 |
| Microsoft.PowerShell.SDK | `UNCHANGED` | 7.6.6 | 7.6.6 |
| Microsoft.PowerShell.Security | `UNCHANGED` | 7.6.6 | 7.6.6 |
| Microsoft.Security.Extensions | `UNCHANGED` | 1.4.0 | 1.4.0 |
| Microsoft.Win32.Registry.AccessControl | `UNCHANGED` | 10.0.5 | 10.0.5 |
| Microsoft.Win32.SystemEvents | `UNCHANGED` | 10.0.5 | 10.0.5 |
| Microsoft.Windows.Compatibility | `UNCHANGED` | 10.0.5 | 10.0.5 |
| Microsoft.WSMan.Management | `UNCHANGED` | 7.6.6 | 7.6.6 |
| Microsoft.WSMan.Runtime | `UNCHANGED` | 7.6.6 | 7.6.6 |
| Newtonsoft.Json | `UNCHANGED` | 13.0.4 | 13.0.4 |
| numpy | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 2.5.4 | 2.5.4 |
| openpyxl | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 3.1.5 | 3.1.5 |
| packaging | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 26.3 | 26.3 |
| pandas | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 3.0.6 | 3.0.6 |
| pip | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 26.2.1 | 26.2.1 |
| pluggy | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 1.6.0 | 1.7.0 |
| Pygments | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 2.21.0 | 2.21.0 |
| pymorphy3 | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 2.0.6 | 2.0.6 |
| pymorphy3-dicts-ru | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 2.4.417150.4580142 | 2.4.417150.4580142 |
| pymupdf | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 1.28.2 | 1.28.2 |
| pytest | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 9.1.1 | 9.1.1 |
| python-dateutil | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 2.9.0.post0 | 2.9.0.post0 |
| Python Embedded | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 3.12.x | 3.12.x |
| pywin32 | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 312 | 312 |
| PyYAML | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 6.0.3 | 6.0.3 |
| RapidFuzz | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 3.14.6 | 3.14.6 |
| runtime.native.System.Data.SqlClient.sni | `UNCHANGED` | 4.4.0 | 4.4.0 |
| runtime.win-x64.runtime.native.System.Data.SqlClient.sni | `UNCHANGED` | 4.4.0 | 4.4.0 |
| setuptools | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 84.0.0 | 84.0.0 |
| six | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 1.17.0 | 1.17.0 |
| SkiaSharp | `UNCHANGED` | 3.119.4 | 3.119.4 |
| SkiaSharp.NativeAssets.Win32 | `UNCHANGED` | 3.119.4 | 3.119.4 |
| System.CodeDom | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.ComponentModel.Composition | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.ComponentModel.Composition.Registration | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.Configuration.ConfigurationManager | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.Data.Odbc | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.Data.OleDb | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.Data.SqlClient | `UNCHANGED` | 4.9.1 | 4.9.1 |
| System.Diagnostics.EventLog | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.Diagnostics.PerformanceCounter | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.DirectoryServices | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.DirectoryServices.AccountManagement | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.DirectoryServices.Protocols | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.Drawing.Common | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.IO.Packaging | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.IO.Ports | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.Management | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.Management.Automation | `UNCHANGED` | 7.6.6 | 7.6.6 |
| System.Net.Http.WinHttpHandler | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.Reflection.Context | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.Runtime.Caching | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.Security.Cryptography.Pkcs | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 10.0.10 | 10.0.13 |
| System.Security.Cryptography.ProtectedData | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.Security.Cryptography.Xml | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 10.0.10 | 10.0.13 |
| System.Security.Permissions | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.ServiceModel.Http | `UNCHANGED` | 10.0.652802 | 10.0.652802 |
| System.ServiceModel.NetFramingBase | `UNCHANGED` | 10.0.652802 | 10.0.652802 |
| System.ServiceModel.NetTcp | `UNCHANGED` | 10.0.652802 | 10.0.652802 |
| System.ServiceModel.Primitives | `UNCHANGED` | 10.0.652802 | 10.0.652802 |
| System.ServiceModel.Syndication | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.ServiceProcess.ServiceController | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.Speech | `UNCHANGED` | 10.0.5 | 10.0.5 |
| System.Web.Services.Description | `UNCHANGED` | 8.1.2 | 8.1.2 |
| System.Windows.Extensions | `UNCHANGED` | 10.0.5 | 10.0.5 |
| Tmds.DBus.Protocol | `UNCHANGED` | 0.94.1 | 0.94.1 |
| tqdm | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 4.70.1 | 4.70.1 |
| tzdata | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 2026.5 | 2026.5 |
| wheel | `VERSION_OR_ARTIFACT_CHANGED_LICENSE_SAME` | 0.48.0 | 0.48.0 |

## Licence rules

The project's own code is read as **Apache-2.0** (LICENSE).

| Component | Licence, as read | Chosen from | In the program as | Licence texts |
|---|---|---|---|---|
| Inter | `OFL-1.1` | - | data | - |
| JetBrains Mono | `OFL-1.1` | - | data | - |
| Microsoft.Management.Infrastructure.Runtime.Win | `not recognised` | - | dynamic_library | - |
| packaging | `BSD-2-Clause` | Apache-2.0 or BSD-2-Clause | python_import | - |
| pymorphy3-dicts-ru | `MIT AND CC-BY-SA-3.0` | - | data | - |
| pymupdf | `GPL-3.0 AND Proprietary` | - | python_import | GPL 3.0: standard text supplied |
| python-dateutil | `not recognised` | - | python_import | - |
| tqdm | `MPL-2.0 AND MIT` | - | python_import | - |
| tzdata | `Apache-2.0` | - | python_import | Apache 2.0: in the component |

Documents the collector added to the pack itself:

- GNU General Public License 3.0 (standard text) - GPL-3.0 asks for a copy of the GPL 3.0: pymupdf

## Scope

Only the explicitly configured project and scan roots were inspected.
No neighboring projects or parent directories were searched.
