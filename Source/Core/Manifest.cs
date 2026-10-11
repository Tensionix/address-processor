using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace AudionAddressProcessor.Core;

/// <summary>
/// The manifest as the console command tells it (address_cli.cmd describe): operations, fields and
/// the layout of the window. The window draws by it and knows no operation by name: a new field or
/// operation of config\tool_manifest.yaml appears in the window by itself, and a kind of field the
/// window does not know is said, not left as an empty place (FieldKinds.Known).
/// </summary>
public sealed class Manifest
{
    public List<Node> Nodes { get; set; } = new();
    public List<Node> Maintenance { get; set; } = new();
    public Layout Layout { get; set; } = new();
    public SlotInfo Slots { get; set; } = new();
    public string Version { get; set; } = "";
    public ProjectPaths Paths { get; set; } = new();

    static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
        NumberHandling = JsonNumberHandling.AllowReadingFromString,
    };

    /// <summary>The answer of "describe" read; an answer that is no manifest throws.</summary>
    public static Manifest Parse(string json)
    {
        var manifest = JsonSerializer.Deserialize<Manifest>(json, Json) ?? throw new JsonException("the command gave no manifest");
        foreach (var node in manifest.Nodes) Bind(node, null);
        foreach (var node in manifest.Maintenance) Bind(node, null);
        return manifest;
    }

    static void Bind(Node node, Node? parent)
    {
        node.Parent = parent;
        foreach (var field in node.Fields) field.Owner = node.Id;
        foreach (var child in node.Children) Bind(child, node);
    }

    /// <summary>Every node, parents before children.</summary>
    public IEnumerable<Node> All() => Nodes.SelectMany(Walk).Concat(Maintenance);

    static IEnumerable<Node> Walk(Node node)
    {
        yield return node;
        foreach (var child in node.Children)
            foreach (var deeper in Walk(child))
                yield return deeper;
    }

    /// <summary>An operation by its id: a node that runs, the first one of the manifest.</summary>
    public Node? Find(string id) => All().FirstOrDefault(node => node.Id == id && node.Runs);

    /// <summary>Every operation: the nodes that run, each id once.</summary>
    public IEnumerable<Node> Operations() => All().Where(node => node.Runs).DistinctBy(node => node.Id);
}

/// <summary>The folders of the project, as the command resolves them.</summary>
public sealed class ProjectPaths
{
    public string Root { get; set; } = "";
    public string Input { get; set; } = "";
    public string Output { get; set; } = "";
    public string Logs { get; set; } = "";
    public string Report { get; set; } = "";
    public string Config { get; set; } = "";
}

/// <summary>The layout of the window: config\window_layout.yaml, checked against the manifest by the command.</summary>
public sealed class Layout
{
    public List<SectionInfo> Sections { get; set; } = new();
    public WorkspaceInfo Workspace { get; set; } = new();
    public List<string> ResultActions { get; set; } = new();
    /// <summary>The signs of the buttons that stand outside the rows of the sections, by operation.</summary>
    public Dictionary<string, string> Icons { get; set; } = new();
}

public sealed class WorkspaceInfo
{
    public string Check { get; set; } = "";
    public string Clear { get; set; } = "";
}

/// <summary>A section of the window: a big button under the header, and the operations of its second row.</summary>
public sealed class SectionInfo
{
    public string Id { get; set; } = "";
    public string Icon { get; set; } = "";
    public string Title { get; set; } = "";
    public string TitleRu { get; set; } = "";
    public string Hint { get; set; } = "";
    public string HintRu { get; set; } = "";
    public List<PlacedOperation> Operations { get; set; } = new();

    [JsonIgnore] public string Name => Lang.Pick(TitleRu, Title);
    [JsonIgnore] public string Line => Lang.Pick(HintRu, Hint);
}

/// <summary>An operation in the row of its section: its short name there (none for an operation alone in its section).</summary>
public sealed class PlacedOperation
{
    public string Id { get; set; } = "";
    public string Icon { get; set; } = "";
    public string Tab { get; set; } = "";
    public string TabRu { get; set; } = "";

    [JsonIgnore] public string TabName => Lang.Pick(TabRu, Tab);
}

/// <summary>The slots of an address: the samples the preview is written with and the short names of the chips.</summary>
public sealed class SlotInfo
{
    public Dictionary<string, string> Samples { get; set; } = new();
    public Dictionary<string, Dictionary<string, string>> ShortLabels { get; set; } = new();

    public string Short(string slot) =>
        ShortLabels.TryGetValue(Lang.Code, out var names) && names.TryGetValue(slot, out var name) ? name
        : ShortLabels.TryGetValue("en", out var english) && english.TryGetValue(slot, out var other) ? other : slot;
}

/// <summary>An operation, or a node that holds operations (a group of the manifest).</summary>
public sealed class Node
{
    public string Id { get; set; } = "";
    public string Title { get; set; } = "";
    public string TitleRu { get; set; } = "";
    public string Description { get; set; } = "";
    public string DescriptionRu { get; set; } = "";
    /// <summary>"safe" or "dangerous": a dangerous one is asked about.</summary>
    public string Kind { get; set; } = "";
    public bool Runs { get; set; }
    public List<Field> Fields { get; set; } = new();
    public List<Node> Children { get; set; } = new();

    [JsonIgnore] public Node? Parent { get; set; }

    [JsonIgnore] public string Name => Lang.Pick(TitleRu, Title);
    [JsonIgnore] public string About => Lang.Pick(DescriptionRu, Description);

    /// <summary>The fields a person fills in: one the manifest keeps for the engine alone (hidden, or a path the working folders hold) is not among them.</summary>
    [JsonIgnore] public IEnumerable<Field> FormFields => Fields.Where(item => item.Drawn);

    /// <summary>The groups of the form in the order their first fields come.</summary>
    public List<FieldGroup> Groups()
    {
        var groups = new List<FieldGroup>();
        foreach (var field in FormFields)
        {
            var group = groups.FirstOrDefault(item => item.Id == field.Group);
            if (group is null) groups.Add(group = new FieldGroup { Id = field.Group });
            group.Fields.Add(field);
        }
        return groups;
    }
}

/// <summary>Fields of one frame of a form.</summary>
public sealed class FieldGroup
{
    public string Id { get; set; } = "";
    public List<Field> Fields { get; } = new();
}

public sealed class Field
{
    public string Id { get; set; } = "";
    /// <summary>checkbox, number, text, radio, select, checkboxes, xlsx_file_picker, slot_preview, slot_order, oktmo_key_toolbar.</summary>
    public string Kind { get; set; } = "";
    public JsonElement Default { get; set; }
    public string Group { get; set; } = "";
    /// <summary>The form shows the field (when its conditions are met).</summary>
    public bool Drawn { get; set; } = true;
    /// <summary>"operation": the value is kept per operation, not for the whole window.</summary>
    public string Scope { get; set; } = "";
    /// <summary>Shown only while every field named here holds something.</summary>
    public List<string> DependsOn { get; set; } = new();
    /// <summary>Shown only while each field named here has the value given.</summary>
    public JsonElement ShowWhen { get; set; }
    /// <summary>
    /// Drawn only while each field named here has the value given - but the engine still gets the value
    /// (the default, when the form does not show it): `show_when` hides a field from the engine too.
    /// </summary>
    public JsonElement DrawWhen { get; set; }
    public string OptionsSource { get; set; } = "";
    public bool Advanced { get; set; }
    public string Label { get; set; } = "";
    public string LabelRu { get; set; } = "";
    public string Hint { get; set; } = "";
    public string HintRu { get; set; } = "";
    public string Placeholder { get; set; } = "";
    public string PlaceholderRu { get; set; } = "";
    public double? Min { get; set; }
    public double? Max { get; set; }
    public double? Step { get; set; }
    public int MinSelected { get; set; }
    public List<Option> Options { get; set; } = new();

    /// <summary>The id of the operation this field belongs to: a field of this name in another operation is another object.</summary>
    [JsonIgnore] public string Owner { get; set; } = "";

    [JsonIgnore] public string Name => Lang.Pick(LabelRu, Label);
    [JsonIgnore] public string Caption => Name;
    [JsonIgnore] public string Tip => Lang.Pick(HintRu, Hint);
    [JsonIgnore] public string PlaceholderText => Lang.Pick(PlaceholderRu, Placeholder);
    [JsonIgnore] public bool HasProvider => OptionsSource.Length > 0;

    /// <summary>What the field's own options look like in the manifest, as the value the form keeps.</summary>
    [JsonIgnore] public bool PerOperation => Scope == "operation";

    /// <summary>The (field, value) conditions of `show_when` and `draw_when`; empty when it has none.</summary>
    public List<(string Field, List<string> Values)> Conditions() => ConditionsOf(ShowWhen).Concat(ConditionsOf(DrawWhen)).ToList();

    static List<(string Field, List<string> Values)> ConditionsOf(JsonElement when)
    {
        var list = new List<(string, List<string>)>();
        if (when.ValueKind != JsonValueKind.Object) return list;
        foreach (var property in when.EnumerateObject())
        {
            var accepted = property.Value.ValueKind == JsonValueKind.Array
                ? property.Value.EnumerateArray().Select(FieldKinds.Text).ToList()
                : new List<string> { FieldKinds.Text(property.Value) };
            list.Add((property.Name, accepted));
        }
        return list;
    }
}

public sealed class Option
{
    public JsonElement Value { get; set; }
    public string Label { get; set; } = "";
    public string LabelRu { get; set; } = "";
    public string ShortLabel { get; set; } = "";
    public string ShortLabelRu { get; set; } = "";
    public string Tooltip { get; set; } = "";
    public string TooltipRu { get; set; } = "";
    public string Hint { get; set; } = "";
    public string HintRu { get; set; } = "";
    public JsonElement Default { get; set; }
    /// <summary>A line that names a group of the options below it, not an option.</summary>
    public bool Header { get; set; }
    /// <summary>The line is pinned by the person (the lists of the OKTMO regions and municipalities): "true" or true.</summary>
    public JsonElement Pinned { get; set; }
    [JsonIgnore] public bool IsPinned => Pinned.ValueKind == JsonValueKind.True || (Pinned.ValueKind == JsonValueKind.String && string.Equals(Pinned.GetString(), "true", StringComparison.OrdinalIgnoreCase));

    [JsonIgnore] public string Name => Lang.Pick(LabelRu, Label);
    [JsonIgnore] public string Caption => Lang.Pick(ShortLabelRu, ShortLabel) is { Length: > 0 } brief ? brief : Name;
    [JsonIgnore] public string Tip => Lang.Pick(TooltipRu, Tooltip) is { Length: > 0 } tip ? tip : Lang.Pick(HintRu, Hint);
    /// <summary>The value as the text the form keeps and compares.</summary>
    [JsonIgnore] public string Key => FieldKinds.Text(Value);
    [JsonIgnore] public bool DefaultOn => Default.ValueKind == JsonValueKind.True;
}

public static class FieldKinds
{
    /// <summary>The kinds of field the window can draw. Anything else fails the self-check of the window.</summary>
    public static readonly string[] Known =
    {
        "checkbox", "number", "text", "radio", "select", "checkboxes", "xlsx_file_picker", "slot_preview", "slot_order", "oktmo_key_toolbar",
    };

    /// <summary>A value of the manifest as text: a number without a tail of zeros, a flag as true or false.</summary>
    public static string Text(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.String => value.GetString() ?? "",
        JsonValueKind.Number => value.GetDouble().ToString("0.############", System.Globalization.CultureInfo.InvariantCulture),
        JsonValueKind.True => "true",
        JsonValueKind.False => "false",
        JsonValueKind.Null or JsonValueKind.Undefined => "",
        _ => value.GetRawText(),
    };
}
