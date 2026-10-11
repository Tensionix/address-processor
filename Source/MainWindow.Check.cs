using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Avalonia.Controls;
using AudionAddressProcessor.Core;

namespace AudionAddressProcessor;

/// <summary>
/// The self-check of the window (--self-check): the manifest is read through the console command
/// and every section, every operation and every form is built - without the window being shown - and
/// what was built is counted against the manifest. An operation without a button, a field without a
/// control or a field of a kind the form does not know fails the check: new fields and operations
/// come into the manifest every week, and an empty place in a form must be an error of a test,
/// not a find of the owner's.
/// The result is a JSON file (logs\gui-self-check.json, or the file named after the key) and the
/// exit code: 0 - everything of the manifest is in the window, 1 - something is not, 2 - the
/// manifest could not be read.
/// </summary>
public partial class MainWindow
{
    /// <summary>The ids of the operations that got a button, as the cards and the service buttons are built.</summary>
    readonly HashSet<string> _withButton = new();

    public async Task<int> SelfCheck(string file)
    {
        var report = new Dictionary<string, object?> { ["version"] = Paths.Version, ["root"] = Paths.Root };
        int code;
        try
        {
            code = await SelfCheck(report);
        }
        catch (Exception ex)
        {
            report["ok"] = false;
            report["error"] = ex.ToString();
            code = 1;
        }
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(file))!);
            File.WriteAllText(file, JsonSerializer.Serialize(report, new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
            }), new UTF8Encoding(false));
        }
        catch { code = code == 0 ? 1 : code; }
        return code;
    }

    async Task<int> SelfCheck(Dictionary<string, object?> report)
    {
        if (Door.Trouble is { Length: > 0 } trouble)
        {
            report["ok"] = false;
            report["error"] = trouble;
            return 2;
        }
        var (manifest, why) = await Door.Describe();
        if (manifest is null)
        {
            report["ok"] = false;
            report["error"] = why;
            return 2;
        }
        _manifest = manifest;
        BuildService();
        BuildSections();

        var builtFields = new Dictionary<string, HashSet<string>>();
        var unknown = new List<string>();
        foreach (var section in manifest.Layout.Sections)
        {
            SelectSection(section);
            foreach (var placed in section.Operations)
            {
                // Every operation of the section is opened in turn: only an open card builds its form.
                SelectOperation(placed);
                if (!builtFields.TryGetValue(placed.Id, out var set)) builtFields[placed.Id] = set = new HashSet<string>();
                set.UnionWith(_form.Built);
                unknown.AddRange(_form.Unknown);
                _form.Unknown.Clear();
            }
        }

        var operations = manifest.Operations().ToList();
        var missingOperations = operations.Where(node => !_withButton.Contains(node.Id)).Select(node => node.Id).ToList();
        var missingFields = new List<string>();
        var kinds = new SortedDictionary<string, int>();
        int fields = 0, fieldsBuilt = 0;
        foreach (var operation in operations)
        {
            builtFields.TryGetValue(operation.Id, out var built);
            foreach (var field in operation.FormFields)
            {
                fields++;
                kinds[field.Kind] = kinds.GetValueOrDefault(field.Kind) + 1;
                if (built is not null && built.Contains(field.Id)) fieldsBuilt++;
                else missingFields.Add(operation.Id + "." + field.Id);
            }
        }
        var unplaced = operations.Select(node => node.Id)
            .Except(manifest.Layout.Sections.SelectMany(section => section.Operations.Select(placed => placed.Id))
                .Concat(manifest.Layout.ResultActions).Append(manifest.Layout.Workspace.Check).Append(manifest.Layout.Workspace.Clear))
            .ToList();

        report["sections"] = manifest.Layout.Sections.Select(section => section.Id).ToList();
        report["operations"] = operations.Count;
        report["operationsWithButton"] = operations.Count - missingOperations.Count;
        report["fields"] = fields;
        report["fieldsBuilt"] = fieldsBuilt;
        report["kinds"] = kinds;
        report["missingOperations"] = missingOperations;
        report["missingFields"] = missingFields;
        report["unknownKinds"] = unknown.Distinct().ToList();
        report["unplaced"] = unplaced;
        bool ok = missingOperations.Count == 0 && missingFields.Count == 0 && unknown.Count == 0 && unplaced.Count == 0;
        report["ok"] = ok;
        return ok ? 0 : 1;
    }
}
