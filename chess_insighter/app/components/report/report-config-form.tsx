import type { Hparams, JsonValue } from "~/lib/types";
import { Input } from "~/components/ui/input";

type Props = {
  value: Hparams;
  onChange: (value: Hparams) => void;
};

export function ReportConfigForm({ value, onChange }: Props) {
  function update(path: string[], next: JsonValue) {
    onChange(updateAtPath(value, path, next) as Hparams);
  }
  return <div className="space-y-5">{Object.entries(value).map(([key, item]) => <ConfigField key={key} path={[key]} name={key} value={item} onChange={update} />)}</div>;
}

function ConfigField({ name, value, path, onChange }: { name: string; value: JsonValue; path: string[]; onChange: (path: string[], value: JsonValue) => void }) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return (
      <section className="rounded-md border border-slate-200 p-4">
        <h3 className="mb-3 text-sm font-semibold capitalize">{label(name)}</h3>
        <div className="grid gap-3 md:grid-cols-2">
          {Object.entries(value).map(([key, item]) => <ConfigField key={key} name={key} value={item} path={[...path, key]} onChange={onChange} />)}
        </div>
      </section>
    );
  }
  if (typeof value === "boolean") {
    return (
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={value} onChange={(event) => onChange(path, event.target.checked)} />
        {label(name)}
      </label>
    );
  }
  if (typeof value === "number") {
    return (
      <label className="block text-sm">
        <span className="mb-1 block text-slate-600">{label(name)}</span>
        <Input type="number" value={value} step="any" onChange={(event) => onChange(path, Number(event.target.value))} />
      </label>
    );
  }
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-slate-600">{label(name)}</span>
      <Input value={String(value ?? "")} onChange={(event) => onChange(path, event.target.value)} />
    </label>
  );
}

function updateAtPath(source: JsonValue, path: string[], next: JsonValue): JsonValue {
  if (path.length === 0) return next;
  if (!source || typeof source !== "object" || Array.isArray(source)) return source;
  const [head, ...tail] = path;
  return {
    ...source,
    [head]: updateAtPath(source[head], tail, next),
  };
}

function label(value: string) {
  return value.replaceAll("_", " ");
}
