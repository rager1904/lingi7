'use client';

import React, { CSSProperties, ReactNode } from 'react';

type BoxProps = {
  children?: ReactNode;
  className?: string;
  style?: CSSProperties;
  gap?: string;
  align?: string;
  justify?: string;
};

const gapValue = (gap?: string) => (gap ? `${Number(gap) * 4}px` : undefined);

export function Stack({ children, className, style, gap, align }: BoxProps) {
  return (
    <div className={className} style={{ display: 'flex', flexDirection: 'column', gap: gapValue(gap), alignItems: align, ...style }}>
      {children}
    </div>
  );
}

export function Flex({ children, className, style, gap, align, justify }: BoxProps) {
  return (
    <div className={className} style={{ display: 'flex', gap: gapValue(gap), alignItems: align, justifyContent: justify === 'between' ? 'space-between' : justify, ...style }}>
      {children}
    </div>
  );
}

export function Card({ children, className, style }: BoxProps) {
  return <section className={className} style={{ borderRadius: 16, padding: 24, background: 'var(--color-surface-raised)', border: '1px solid var(--color-border-base)', boxShadow: 'inset 0 1px 0 rgba(255,255,255,.045)', ...style }}>{children}</section>;
}

export function Text({ children, className, style }: BoxProps & { kind?: string }) {
  return <span className={className} style={style}>{children}</span>;
}

export function Button({ children, className, style, disabled, onClick, kind = 'secondary', size = 'medium' }: any) {
  return (
    <button className={className} style={{ borderRadius: 10, border: '1px solid var(--color-border-base)', padding: size === 'small' ? '6px 10px' : size === 'large' ? '12px 16px' : '10px 14px', color: 'var(--text-color-primary)', background: kind === 'primary' ? 'var(--color-accent)' : 'var(--color-surface-base)', cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.55 : 1, ...style }} disabled={disabled} onClick={onClick} type="button">
      {children}
    </button>
  );
}

export function Spinner({ description, ...props }: any) {
  return <div {...props} style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}><span className="ui-spinner" aria-hidden="true" />{description && <span>{description}</span>}</div>;
}

export function TextInput(props: any) {
  return <input {...props} style={{ width: '100%', borderRadius: 8, padding: 10, border: '1px solid var(--color-border-base)', background: 'var(--color-surface-base)', color: 'var(--text-color-primary)', ...(props.style || {}) }} />;
}

export function TextArea({ attributes, resizeable, ...props }: any) {
  return <textarea {...props} {...(attributes?.TextAreaElement || {})} style={{ width: '100%', borderRadius: 8, padding: 10, border: '1px solid var(--color-border-base)', background: 'var(--color-surface-base)', color: 'var(--text-color-primary)', resize: resizeable === 'manual' ? 'vertical' : undefined, ...(props.style || {}) }} />;
}

export function FormField({ slotLabel, children }: any) {
  const fieldProps = { id: String(slotLabel).toLowerCase().replace(/\s+/g, '-') };
  return <label style={{ display: 'block' }}><span style={{ display: 'block', marginBottom: 8, color: 'var(--text-color-secondary)' }}>{slotLabel}</span>{typeof children === 'function' ? children(fieldProps) : children}</label>;
}

export function Select({ items, value, onValueChange, disabled }: any) {
  return <select value={value} disabled={disabled} onChange={(event) => onValueChange?.(event.target.value)} style={{ width: '100%', borderRadius: 8, padding: 12, background: 'var(--color-surface-base)', color: 'var(--text-color-primary)', border: '1px solid var(--color-border-base)' }}>{items?.map((item: any) => <option key={item.value} value={item.value}>{item.children}</option>)}</select>;
}

export function Switch({ checked, onCheckedChange, disabled }: any) {
  return <input type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onCheckedChange?.(event.target.checked)} />;
}

export function Tooltip({ children, slotContent }: any) {
  return <span title={slotContent}>{children}</span>;
}

export function AppBar({ slotLeft, slotRight }: any) {
  return <header className="app-bar"><div>{slotLeft}</div><div>{slotRight}</div></header>;
}

export function Tabs({ items }: any) {
  const [active, setActive] = React.useState(items?.[0]?.value);
  const current = items?.find((item: any) => item.value === active) || items?.[0];
  return <div><div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>{items?.map((item: any) => <Button key={item.value} kind={item.value === active ? 'primary' : 'secondary'} onClick={() => setActive(item.value)}>{item.children}</Button>)}</div>{current?.slotContent}</div>;
}

export function Accordion({ items }: any) {
  return <div>{items?.map((item: any) => <details key={item.value} style={{ padding: 12, borderBottom: '1px solid var(--color-border-base)' }}><summary>{item.slotTrigger}</summary><div style={{ paddingTop: 12 }}>{item.slotContent}</div></details>)}</div>;
}

export function SegmentedControl({ items, value, onValueChange }: any) {
  return <div style={{ display: 'inline-flex', gap: 4 }}>{items?.map((item: any) => <Button key={item.value} kind={item.value === value ? 'primary' : 'secondary'} size="small" onClick={() => onValueChange?.(item.value)}>{item.children}</Button>)}</div>;
}

export function Modal({ open, onOpenChange, slotHeading, slotFooter, children, style }: any) {
  if (!open) return null;
  return <div className="modal-backdrop" onClick={() => onOpenChange?.(false)}><div className="modal-panel" style={style} onClick={(event) => event.stopPropagation()}><Flex justify="between" align="center"><Text>{slotHeading}</Text><Button size="small" onClick={() => onOpenChange?.(false)}>Close</Button></Flex><div style={{ marginTop: 16 }}>{children}</div><div style={{ marginTop: 16 }}>{slotFooter}</div></div></div>;
}

export function Nebula(_props: { variant?: string }) {
  return <div className="local-nebula" data-testid="local-nebula" />;
}
