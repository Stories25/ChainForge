import React, {
  useState,
  useCallback,
  forwardRef,
  useImperativeHandle,
  useEffect,
} from "react";
import { Button, Flex, Modal, Popover, Select, Tooltip } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import emojidata from "@emoji-mart/data";
import Picker from "@emoji-mart/react";
// react-jsonschema-form
import validator from "@rjsf/validator-ajv8";
import Form from "@rjsf/core";
import { WidgetProps, FieldTemplateProps } from "@rjsf/utils";
import {
  ModelSettings,
  getDefaultModelFormData,
  postProcessFormData,
} from "./ModelSettingSchemas";
import {
  Dict,
  JSONCompatible,
  LLMSpec,
  ModelSettingsDict,
} from "./backend/typing";
import { IconHeart } from "@tabler/icons-react";
import { APP_IS_RUNNING_LOCALLY } from "./backend/utils";
import { fetchEnvironAPIKeys } from "./backend/backend";
import {
  ZEN_MODEL_CATALOG,
  ZEN_PROVIDERS,
  sortZenModelsNewestFirst,
  zenModelDropdownLabel,
  zenModelInfo,
  zenProviderModels,
} from "./zenModels";

const IS_RUNNING_LOCALLY = APP_IS_RUNNING_LOCALLY();

// Custom UI widgets for react-jsonschema-form
export const DatalistWidget = (props: WidgetProps) => {
  const [data, setData] = useState(
    (
      props.options.enumOptions?.map((option, index) => ({
        value: option.value,
        label: option.value,
      })) ?? []
    ).concat(
      props.options.enumOptions?.find((o) => o.value === props.value)
        ? []
        : { value: props.value, label: props.value },
    ),
  );

  return (
    <Select
      data={data}
      defaultValue={props.value ?? ""}
      onChange={(newVal) => props.onChange(newVal ?? "")}
      size="sm"
      placeholder="Select items"
      nothingFound="Nothing found"
      searchable
      creatable
      getCreateLabel={(query) => `+ Create ${query}`}
      onCreate={(query) => {
        const item = { value: query, label: query };
        setData((current) => [...current, item]);
        console.log(item);
        return item;
      }}
    />
  );
};

/**
 * Minimal range widget matching the mock design: just the slider. The live
 * value is shown next to the field's label (see MockStyleFieldTemplate).
 */
export const MockRangeWidget = (props: WidgetProps) => {
  const { schema, value, onChange, disabled, readonly, required, id, name } =
    props;
  const min = schema.minimum ?? 0;
  const max = schema.maximum ?? 100;
  const step = schema.multipleOf ?? 1;
  return (
    <input
      type="range"
      id={id}
      name={name}
      min={min}
      max={max}
      step={step}
      value={typeof value === "number" ? value : min}
      disabled={disabled}
      readOnly={readonly}
      required={required}
      onChange={(e) => onChange(Number(e.target.value))}
      style={{
        width: "100%",
        accentColor: "#4299e1",
        cursor: disabled ? "not-allowed" : "pointer",
      }}
    />
  );
};

/**
 * Custom widget for the OpenCode Zen model field (mock A): a read-only display
 * of the node's currently selected model. Model changes happen on the node's
 * model list, not in the settings modal.
 */
const DisabledModelWidget = (props: WidgetProps) => {
  return (
    <Select
      data={[{ value: props.value ?? "", label: props.value ?? "" }]}
      value={props.value ?? ""}
      disabled
      size="sm"
      onChange={() => {}}
    />
  );
};

/**
 * Custom widget for the OpenCode Zen model field: a provider dropdown on top
 * (OpenAI, Anthropic, Zhipu, ...) that narrows a searchable model dropdown
 * below it. Models are sorted by release date, newest first, and each is
 * labelled with its per-1M-token pricing. Selecting a model updates the
 * node's model on submit.
 */
const ZenModelWidget = (props: WidgetProps) => {
  const value = (props.value as string) ?? "";
  const info = zenModelInfo(value);

  // The provider follows the current model's catalogue category; an empty
  // value defaults to the first provider.
  const activeProvider =
    info?.category ?? (value === "" ? ZEN_PROVIDERS[0].category : null);

  const models = activeProvider
    ? zenProviderModels(activeProvider)
    : sortZenModelsNewestFirst(ZEN_MODEL_CATALOG);
  const modelData = models.map((m) => ({
    value: m.id,
    label: zenModelDropdownLabel(m.id),
  }));
  // Keep an out-of-catalogue value visible and selectable.
  if (value && !info) modelData.unshift({ value, label: value });

  return (
    <div>
      <Select
        label="Provider"
        data={ZEN_PROVIDERS.map((p) => ({
          value: p.category,
          label: p.label,
        }))}
        value={activeProvider}
        placeholder="Select a provider"
        size="sm"
        onChange={(category) => {
          // Switching providers jumps to that provider's newest model.
          const newest = category ? zenProviderModels(category)[0] : undefined;
          if (newest) props.onChange(newest.id);
        }}
      />
      <Select
        label="Model"
        data={modelData}
        value={value}
        searchable
        size="sm"
        mt={10}
        onChange={(v) => props.onChange(v ?? "")}
      />
    </div>
  );
};

/**
 * Textarea widget matching the mock design: monospace, dark, resizable.
 */
export const MockTextareaWidget = (props: WidgetProps) => {
  const {
    id,
    value,
    required,
    disabled,
    readonly,
    autofocus,
    onChange,
    options,
    placeholder,
  } = props;
  return (
    <textarea
      id={id}
      value={value ?? ""}
      placeholder={placeholder}
      required={required}
      disabled={disabled}
      readOnly={readonly}
      // eslint-disable-next-line jsx-a11y/no-autofocus
      autoFocus={autofocus}
      rows={3}
      onChange={(e) =>
        onChange(e.target.value === "" ? options.emptyValue : e.target.value)
      }
      style={{
        width: "100%",
        minHeight: "64px",
        resize: "vertical",
        background: "var(--panel, #1e1e2e)",
        border: "1px solid var(--border-color, #555)",
        borderRadius: "6px",
        color: "inherit",
        padding: "7px 10px",
        fontSize: "13px",
        fontFamily: 'Consolas, "Cascadia Code", monospace',
      }}
    />
  );
};

const widgets = {
  datalist: DatalistWidget,
  disabledModel: DisabledModelWidget,
  zenModel: ZenModelWidget,
  range: MockRangeWidget,
  textarea: MockTextareaWidget,
};

/**
 * Field template matching the mock design: each setting renders as a block of
 * [label → control → help text], with the help text drawn from the schema's
 * description (plus any ui:help supplement). Fields whose widget is "hidden"
 * render nothing.
 *
 * Mock extras:
 *  - Range fields show their live value in monospace next to the label.
 *  - Textarea fields show a live char count ahead of the help text.
 */
const MockStyleFieldTemplate = (props: FieldTemplateProps) => {
  const {
    id,
    label,
    help,
    rawHelp,
    required,
    children,
    displayLabel,
    schema,
    errors,
    formData,
    uiSchema,
  } = props;
  if (schema?.["ui:widget"] === "hidden" || !displayLabel)
    return <>{children}</>;

  const widget = uiSchema?.["ui:widget"];

  // Live value for range fields, e.g. "temperature 0.7" in the label row.
  const rangeValue =
    widget === "range" && typeof formData === "number"
      ? String(formData)
      : undefined;

  // Live char count for textarea fields, e.g. "68 chars · <help>".
  const charCount =
    widget === "textarea" && typeof formData === "string"
      ? formData.length
      : undefined;

  // Help text: the schema's description, supplemented by any ui:help. (rjsf
  // only surfaces ui:help here, but the mock draws the full description.)
  const helpParts: string[] = [];
  if (typeof schema.description === "string" && schema.description)
    helpParts.push(schema.description);
  if (typeof rawHelp === "string" && rawHelp && !helpParts.includes(rawHelp))
    helpParts.push(rawHelp);
  const helpText = helpParts.join(" ");

  return (
    <div style={{ marginBottom: "16px" }}>
      <label
        htmlFor={id}
        style={{
          display: "block",
          fontWeight: 600,
          fontSize: "13px",
          marginBottom: "6px",
        }}
      >
        {label}
        {rangeValue !== undefined && (
          <span
            style={{
              fontFamily: "Consolas, monospace",
              fontWeight: 400,
              fontSize: "12px",
              color: "#4299e1",
              marginLeft: "8px",
            }}
          >
            {rangeValue}
          </span>
        )}
        {required && <span style={{ color: "#e46161" }}> *</span>}
      </label>
      {children}
      {(helpText.length > 0 || help) && (
        <div
          style={{
            fontSize: "12px",
            color: "var(--tooltip-text-color, #aaa)",
            marginTop: "4px",
            opacity: 0.85,
          }}
        >
          {charCount !== undefined ? (
            <>
              {helpText.length > 0 ? (
                <>
                  {charCount} chars · {helpText}
                </>
              ) : (
                <>{charCount} chars</>
              )}
            </>
          ) : helpText.length > 0 ? (
            <>{helpText}</>
          ) : (
            help
          )}
        </div>
      )}
      {errors}
    </div>
  );
};

export interface ModelSettingsModalRef {
  trigger: () => void;
}
export interface ModelSettingsModalProps {
  model?: LLMSpec;
  onSettingsSubmit?: (
    savedItem: LLMSpec,
    formData: Dict<JSONCompatible>,
    settingsData: Dict<JSONCompatible>,
    makeFavorite?: boolean,
  ) => void;
}
type FormData = LLMSpec["formData"];

const ModelSettingsModal = forwardRef<
  ModelSettingsModalRef,
  ModelSettingsModalProps
>(function ModelSettingsModal({ model, onSettingsSubmit }, ref) {
  const [opened, { open, close }] = useDisclosure(false);

  const [formData, setFormData] = useState<FormData>(undefined);

  const [schema, setSchema] = useState<ModelSettingsDict["schema"]>({
    type: "object",
    description: "No model info object was passed to settings modal.",
    required: [],
    properties: {},
  });
  const [uiSchema, setUISchema] = useState<ModelSettingsDict["uiSchema"]>({});
  const [baseModelName, setBaseModelName] = useState("(unknown)");

  const [initShortname, setInitShortname] = useState<string | undefined>(
    undefined,
  );
  const [initModelName, setInitModelName] = useState<string | undefined>(
    undefined,
  );

  // Totally necessary emoji picker
  const [modelEmoji, setModelEmoji] = useState("");
  const [emojiPickerOpen, setEmojiPickerOpen] = useState<boolean>(false);

  // Name of the env var holding the provider's API key, if the key is missing
  // from the environment. Null when the key is present (or unknown).
  const [missingAPIKeyEnv, setMissingAPIKeyEnv] = useState<string | null>(null);

  // Mock C: the user can paste an API key for this session; it travels with
  // the call kwargs (api_key) instead of the environment.
  const [pastedAPIKey, setPastedAPIKey] = useState<string>("");

  // Fixed base URL the provider always targets, if it declares one. Shown
  // (disabled) in the missing-key state, like the mock.
  const [baseUrlDisplay, setBaseUrlDisplay] = useState<string | undefined>(
    undefined,
  );

  // A pasted key enables Submit/Favorite once it looks plausible (mock C:
  // at least 4 characters).
  const pastedAPIKeyValid =
    missingAPIKeyEnv !== null && pastedAPIKey.trim().length >= 4;

  // Check whether the provider's declared API key is set in the environment
  // (mirrors the missing-API-key mock state). Only possible when running
  // locally, where the Flask server can read the environment. The endpoint
  // returns keys keyed by provider alias (e.g. "OpenCode_Zen"); we accept
  // either the alias or the raw env-var name.
  useEffect(() => {
    let cancelled = false;
    setMissingAPIKeyEnv(null);
    if (!IS_RUNNING_LOCALLY || !model?.base_model) return;
    const settingsSpec = ModelSettings[model.base_model];
    const envVar = settingsSpec?.api_key_env;
    if (!envVar) return;
    const alias = settingsSpec.fullName
      .replace(" (custom provider)", "")
      .replace(/\s+/g, "_");
    fetchEnvironAPIKeys()
      .then((keys) => {
        const hasKey =
          (alias in keys && keys[alias]) || (envVar in keys && keys[envVar]);
        if (!cancelled && !hasKey) setMissingAPIKeyEnv(envVar);
      })
      .catch(() => {
        /* Can't tell; assume the key is there and let run-time surface errors. */
      });
    return () => {
      cancelled = true;
    };
  }, [model]);

  useEffect(() => {
    if (model && model.base_model) {
      setModelEmoji(model.emoji);
      setPastedAPIKey("");
      setBaseUrlDisplay(undefined);
      if (!(model.base_model in ModelSettings)) {
        setSchema({
          type: "object",
          description: `Did not find settings schema for base model ${model.base_model}. Maybe you are missing importing a custom provider script?`,
          required: [],
          properties: {},
        });
        setUISchema({});
        setBaseModelName(model.base_model);
        return;
      }
      const settingsSpec = ModelSettings[model.base_model];
      const schema = settingsSpec.schema;
      setBaseUrlDisplay(settingsSpec.base_url);
      setSchema(schema);
      setUISchema(settingsSpec.uiSchema);
      setBaseModelName(settingsSpec.fullName.replace(" (custom provider)", ""));

      // If the user has already saved custom settings...
      if (model.formData) {
        setFormData(model.formData);
        setInitShortname(model.formData.shortname as string | undefined);

        // If the "custom_model" field is set, use that as the initial model name, overriding "model".
        // if (string_exists(model.formData.custom_model))
        // setInitModelName(model.formData.custom_model as string);
        // else
        setInitModelName(model.formData.model as string | undefined);
      } else {
        // Create settings from schema
        const default_settings: Dict<JSONCompatible | undefined> = {};
        Object.keys(schema.properties).forEach((key) => {
          default_settings[key] =
            "default" in schema.properties[key]
              ? schema.properties[key].default
              : undefined;
        });
        setInitShortname(default_settings.shortname?.toString());
        setInitModelName(default_settings.model?.toString());
        setFormData(getDefaultModelFormData(settingsSpec));
      }
    }
  }, [model]);

  // Postprocess the form data into the format expected by the backend (kwargs passed to Python API calls)
  const postprocess = useCallback(
    (fdata: FormData) => {
      if (model === undefined) return {};
      const settings_data = postProcessFormData(
        ModelSettings[model.base_model],
        fdata ?? {},
      );
      // A key pasted for this session (mock C) rides along with the kwargs.
      if (pastedAPIKeyValid) settings_data.api_key = pastedAPIKey.trim();
      return settings_data;
    },
    [model, pastedAPIKeyValid, pastedAPIKey],
  );

  const saveFormState = useCallback(
    (fdata: FormData, makeFavorite?: boolean) => {
      if (fdata === undefined) return;
      // For some reason react-json-form-schema returns 'undefined' on empty strings.
      // We need to (1) detect undefined values for keys in formData and (2) if they are of type string, replace with "",
      // if that property is marked with a special "allow_empty_str" property.
      const patched_fdata: FormData = {};
      Object.entries(fdata).forEach(([key, val]) => {
        if (
          val === undefined &&
          key in schema.properties &&
          schema.properties[key].allow_empty_str === true
        )
          patched_fdata[key] = "";
        else patched_fdata[key] = val;
      });

      setFormData(patched_fdata);

      if (onSettingsSubmit && model !== undefined) {
        model.emoji = modelEmoji;
        onSettingsSubmit(
          model,
          patched_fdata,
          postprocess(patched_fdata),
          makeFavorite,
        );
      }
    },
    [model, modelEmoji, schema, setFormData, onSettingsSubmit, postprocess],
  );

  const onSubmit = useCallback(
    (submitInfo: LLMSpec) => {
      saveFormState(submitInfo.formData);
    },
    [saveFormState],
  );

  // On every edit to the form...
  const onFormDataChange = (state: LLMSpec) => {
    if (state && state.formData) {
      // This checks if the model name has changed, but the shortname wasn't edited (in this window).
      // In this case, we auto-change the shortname, to save user's time and nickname models appropriately.
      const modelname = state.formData.model as string | undefined;
      const shortname = state.formData.shortname as string | undefined;
      if (shortname === initShortname && modelname !== initModelName) {
        // Only change the shortname if there is a distinct model name.
        // If not, let the shortname remain the same for this time, and just remember the model name.
        if (initModelName !== undefined) {
          const shortname_map = schema.properties?.model
            ?.shortname_map as Dict<string>;
          if (
            shortname_map &&
            modelname !== undefined &&
            modelname in shortname_map
          )
            state.formData.shortname = shortname_map[modelname];
          else state.formData.shortname = modelname?.split("/").at(-1);
          setInitShortname(shortname);
        }

        setInitModelName(modelname);
      }

      setFormData(state.formData);
    }
  };

  const onClickSubmit = useCallback(
    (makeFavorite?: boolean) => {
      if (formData) saveFormState(formData, makeFavorite);
      close();
    },
    [formData, close, saveFormState],
  );

  const onEmojiSelect = useCallback(
    (selection: Dict) => {
      const emoji = selection.native;
      setModelEmoji(emoji);
      setEmojiPickerOpen(false);
    },
    [setModelEmoji, setEmojiPickerOpen],
  );

  // This gives the parent access to triggering the modal
  const trigger = useCallback(() => {
    open();
  }, [schema, uiSchema, baseModelName, open]);
  useImperativeHandle(ref, () => ({
    trigger,
  }));

  // Custom providers get the mock's green provider name + SCHEMA v2 badge.
  const isCustomProvider = !!model?.base_model?.startsWith("__custom");

  return (
    <Modal.Root size="lg" opened={opened} onClose={() => onClickSubmit(false)}>
      <Modal.Overlay />
      <Modal.Content>
        <Modal.Header>
          <Modal.Title>
            <div className="nowheel nodrag">
              <Popover
                width={200}
                position="bottom"
                withArrow
                shadow="md"
                withinPortal
                opened={emojiPickerOpen}
                onChange={setEmojiPickerOpen}
              >
                <Popover.Target>
                  <Button
                    variant="subtle"
                    compact
                    style={{ fontSize: "21px" }}
                    onClick={() => {
                      setEmojiPickerOpen((o: boolean) => !o);
                    }}
                  >
                    {modelEmoji}
                  </Button>
                </Popover.Target>
                <Popover.Dropdown>
                  <Picker
                    data={emojidata}
                    onEmojiSelect={onEmojiSelect}
                    theme="light"
                  />
                </Popover.Dropdown>
              </Popover>
              <span>
                {"Model Settings: "}
                <span
                  style={isCustomProvider ? { color: "#7ee2a8" } : undefined}
                >
                  {baseModelName}
                </span>
              </span>
              {isCustomProvider && (
                <span
                  style={{
                    fontSize: "10px",
                    fontWeight: 700,
                    letterSpacing: "0.4px",
                    padding: "1px 7px",
                    borderRadius: "8px",
                    marginLeft: "8px",
                    background: "rgba(126,226,168,0.15)",
                    color: "#7ee2a8",
                    border: "1px solid rgba(126,226,168,0.4)",
                  }}
                >
                  SCHEMA v2
                </span>
              )}
            </div>
          </Modal.Title>

          <Flex justify="right">
            <Modal.CloseButton />
          </Flex>
        </Modal.Header>
        <Modal.Body>
          {missingAPIKeyEnv && (
            <div
              style={{
                background: "rgba(228,97,97,0.12)",
                border: "1px solid #e46161",
                borderRadius: "8px",
                padding: "10px 14px",
                fontSize: "13px",
                color: "#e46161",
                marginBottom: "16px",
              }}
            >
              {"⚠ "}
              <b>{missingAPIKeyEnv}</b>
              {" is not set. Get a key from the provider and add it to your "}
              <b>environment</b>
              {" or a project-root "}
              <code>.env</code>
              {
                " file, then restart ChainForge — or paste the key below for this session. Opening settings for the provider after saving the key will clear this warning."
              }
            </div>
          )}
          {missingAPIKeyEnv && (
            <div style={{ marginBottom: "16px" }}>
              <label
                style={{
                  display: "block",
                  fontWeight: 600,
                  fontSize: "13px",
                  marginBottom: "6px",
                }}
              >
                {missingAPIKeyEnv}
              </label>
              <input
                type="password"
                value={pastedAPIKey}
                placeholder={`Paste ${missingAPIKeyEnv} for this session`}
                onChange={(e) => setPastedAPIKey(e.target.value)}
                style={{
                  width: "100%",
                  background: "var(--panel, #1e1e2e)",
                  border: "1px solid var(--border-color, #555)",
                  borderRadius: "6px",
                  color: "inherit",
                  padding: "7px 10px",
                  fontSize: "13px",
                  fontFamily: "inherit",
                }}
              />
              <div
                style={{
                  fontSize: "12px",
                  color: "var(--tooltip-text-color, #aaa)",
                  marginTop: "4px",
                  opacity: 0.85,
                }}
              >
                {
                  "Read from the environment (auto-loaded from a project-root .env file) or paste it here for this session. Submit unlocks once the key looks valid."
                }
              </div>
            </div>
          )}
          {missingAPIKeyEnv && baseUrlDisplay && (
            <div style={{ marginBottom: "16px" }}>
              <label
                style={{
                  display: "block",
                  fontWeight: 600,
                  fontSize: "13px",
                  marginBottom: "6px",
                }}
              >
                Base URL (fixed)
              </label>
              <input
                type="text"
                value={baseUrlDisplay}
                disabled
                style={{
                  width: "100%",
                  background: "var(--panel, #1e1e2e)",
                  border: "1px solid var(--border-color, #555)",
                  borderRadius: "6px",
                  color: "var(--tooltip-text-color, #aaa)",
                  padding: "7px 10px",
                  fontSize: "13px",
                  fontFamily: "Consolas, monospace",
                }}
              />
              <div
                style={{
                  fontSize: "12px",
                  color: "var(--tooltip-text-color, #aaa)",
                  marginTop: "4px",
                  opacity: 0.85,
                }}
              >
                {
                  "Hard-coded in the provider: the client always targets this endpoint — no per-user override, by design."
                }
              </div>
            </div>
          )}
          <Form
            schema={schema}
            uiSchema={uiSchema}
            widgets={widgets} // Custom UI widgets
            templates={{ FieldTemplate: MockStyleFieldTemplate }}
            formData={formData}
            // // @ts-expect-error This is literally the example code from react-json-schema; no idea why it wouldn't typecheck correctly.
            validator={validator}
            // @ts-expect-error Expect format is LLMSpec.
            onChange={onFormDataChange}
            // @ts-expect-error Expect format is LLMSpec.
            onSubmit={onSubmit}
            style={{ width: "100%" }}
          >
            <Flex justify="right" gap="sm" style={{ marginTop: "8px" }}>
              {IS_RUNNING_LOCALLY && (
                <Tooltip
                  label="Save as a favorite. Uses the nickname, so make sure it's good."
                  withArrow
                  multiline
                  maw="220px"
                >
                  <Button
                    title="Favorite"
                    fw="normal"
                    variant="outline"
                    size="xs"
                    color="gray"
                    disabled={!!missingAPIKeyEnv && !pastedAPIKeyValid}
                    rightIcon={<IconHeart size="12pt" />}
                    onClick={() => {
                      // Submit the form and make the saved model settings a favorite
                      onClickSubmit(true);
                    }}
                  >
                    Favorite
                  </Button>
                </Tooltip>
              )}
              <Button
                title="Submit"
                disabled={!!missingAPIKeyEnv && !pastedAPIKeyValid}
                onClick={() => onClickSubmit(false)}
              >
                Submit
              </Button>
            </Flex>
          </Form>
        </Modal.Body>
      </Modal.Content>
    </Modal.Root>
  );
});

export default ModelSettingsModal;
