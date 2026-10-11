using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace AudionAddressProcessor.Core;

/// <summary>
/// The values of the fields, by the id of a field and not by the operation: the address columns
/// set for the collection stay when the reference is normalised - one field, one value (the rule
/// of the window before this one). A field the manifest marks `scope: operation` is the exception:
/// another operation has a field of this name with other options. The values live as long as the
/// window and are not written to the disk - every start begins with the defaults of the manifest.
/// A value is kept as text: a flag as "true" or "false", a number without a tail of zeros, a group
/// of flags as its values joined by a line break, the order of the slots as a JSON object.
/// </summary>
public sealed class Values
{
    readonly Dictionary<string, string> _held = new();

    /// <summary>A value was changed: the key of its field.</summary>
    public event Action<Field>? Changed;

    public const char ListSeparator = '\n';

    /// <summary>The key a value is kept under: the id of the field, with the operation in front of it for a field kept per operation.</summary>
    public static string KeyOf(Field field) => field.PerOperation ? field.Owner + ":" + field.Id : field.Id;

    static string Key(Field field) => KeyOf(field);

    /// <summary>The default of a field as the text this class keeps.</summary>
    public static string DefaultOf(Field field)
    {
        var value = field.Default;
        switch (field.Kind)
        {
            case "checkboxes":
                return value.ValueKind == JsonValueKind.Array ? string.Join(ListSeparator, value.EnumerateArray().Select(FieldKinds.Text)) : "";
            case "slot_order":
                return value.ValueKind == JsonValueKind.Object ? value.GetRawText() : "{}";
            default:
                return FieldKinds.Text(value);
        }
    }

    public string Get(Field field) => _held.TryGetValue(Key(field), out var value) ? value : DefaultOf(field);

    public bool IsOn(Field field) => Get(field) == "true";

    public HashSet<string> Picked(Field field) =>
        Get(field).Split(ListSeparator, StringSplitOptions.RemoveEmptyEntries).ToHashSet();

    /// <summary>Not the default of the manifest: what was set for this run.</summary>
    public bool IsChanged(Field field)
    {
        var now = Get(field);
        var was = DefaultOf(field);
        if (now == was) return false;
        // The same slots in the same places, written otherwise, are not a change; nor is the same set of ticks in another order.
        return field.Kind switch
        {
            "slot_order" => !SameOrder(now, was),
            "checkboxes" => !Picked(field).SetEquals(was.Split(ListSeparator, StringSplitOptions.RemoveEmptyEntries)),
            _ => true,
        };
    }

    static bool SameOrder(string a, string b)
    {
        try
        {
            using var left = JsonDocument.Parse(a);
            using var right = JsonDocument.Parse(b);
            var one = left.RootElement.EnumerateObject().ToDictionary(item => item.Name, item => item.Value.ToString());
            var other = right.RootElement.EnumerateObject().ToDictionary(item => item.Name, item => item.Value.ToString());
            return one.Count == other.Count && one.All(item => other.TryGetValue(item.Key, out var value) && value == item.Value);
        }
        catch { return false; }
    }

    public void Set(Field field, string value)
    {
        if (Get(field) == value) return;
        // A value equal to the default is not held: another operation with the same field id and
        // another default keeps its own default.
        if (value == DefaultOf(field)) _held.Remove(Key(field));
        else _held[Key(field)] = value;
        Changed?.Invoke(field);
    }

    /// <summary>Back to the defaults of the manifest.</summary>
    public void Reset(IEnumerable<Field> fields)
    {
        foreach (var field in fields)
        {
            if (!_held.Remove(Key(field))) continue;
            Changed?.Invoke(field);
        }
    }

    // ------------------------------------------------------------ what is in sight

    /// <summary>
    /// Whether the form shows a field now: `depends_on` - while each field named holds something,
    /// `show_when` - while each has the value given. The rule is that of the console command
    /// (operation_model.dependencies_met), which sends nothing of a field that is not in sight.
    /// </summary>
    public bool IsShown(Node node, Field field)
    {
        foreach (var name in field.DependsOn)
        {
            var held = Of(node, name) is { } other ? Get(other).Trim().ToLowerInvariant() : "";
            if (held is "" or "0" or "false" or "none" or "null") return false;
        }
        foreach (var (name, accepted) in field.Conditions())
        {
            var actual = Of(node, name) is { } other ? Get(other) : "";
            if (!accepted.Contains(actual)) return false;
        }
        return true;
    }

    static Field? Of(Node node, string id) => node.Fields.FirstOrDefault(field => field.Id == id);

    // ------------------------------------------------------------ the command

    /// <summary>
    /// The values of an operation as the command reads them (--params): every field of its form by
    /// its id, in the type the field has - a flag, a number, a list, an object, a text. An untouched
    /// field goes with the default of the manifest exactly as the manifest wrote it. The preview
    /// of the address line and the toolbar of the OKTMO keys are drawn, not given: they are not sent.
    /// </summary>
    public string ForDoor(Node node)
    {
        var payload = new JsonObject();
        foreach (var field in node.FormFields)
        {
            if (field.Kind is "slot_preview" or "oktmo_key_toolbar") continue;
            if (!IsChanged(field)) { payload[field.Id] = JsonNode.Parse(DefaultJson(field)); continue; }
            var text = Get(field);
            payload[field.Id] = field.Kind switch
            {
                "checkbox" => JsonValue.Create(text == "true"),
                "number" => Number(text),
                "checkboxes" => new JsonArray(text.Split(ListSeparator, StringSplitOptions.RemoveEmptyEntries).Select(item => (JsonNode?)JsonValue.Create(item)).ToArray()),
                "slot_order" => JsonNode.Parse(text),
                // A choice goes as the manifest wrote its value: a number stays a number.
                "radio" or "select" => field.Options.FirstOrDefault(option => option.Key == text) is { } option
                    ? JsonNode.Parse(option.Value.GetRawText()) : JsonValue.Create(text),
                _ => JsonValue.Create(text),
            };
        }
        return payload.ToJsonString(new JsonSerializerOptions
        {
            WriteIndented = true,
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        });
    }

    static string DefaultJson(Field field) =>
        field.Default.ValueKind == JsonValueKind.Undefined ? (field.Kind == "checkboxes" ? "[]" : "\"\"") : field.Default.GetRawText();

    static JsonNode Number(string text)
    {
        if (!double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out var number)) return JsonValue.Create(text);
        return number == Math.Floor(number) && Math.Abs(number) < 1e15 ? JsonValue.Create((long)number) : JsonValue.Create(number);
    }

    /// <summary>The fields of an operation that are not at their defaults, as "--set" would name them.</summary>
    public Dictionary<string, string> ChangedOf(Node node)
    {
        var changed = new Dictionary<string, string>();
        foreach (var field in node.FormFields)
        {
            if (field.Kind is "slot_preview" or "oktmo_key_toolbar" || !IsChanged(field)) continue;
            changed[field.Id] = field.Kind == "checkboxes" ? Get(field).Replace(ListSeparator, ',') : Get(field);
        }
        return changed;
    }
}
