import type { ReactNode, TableHTMLAttributes, TdHTMLAttributes } from "react";
import "./cardTable.css";

type CardTableProps = TableHTMLAttributes<HTMLTableElement> & {
  children: ReactNode;
  /** Optional accessible name when the surrounding card does not provide one. */
  caption?: string;
};

/** A table that becomes a labelled card list below 720px. The wrapper is the same
 *  overflow container used by the existing wide tables, so desktop behaviour is unchanged. */
export function CardTable({ children, className = "", caption, ...rest }: CardTableProps) {
  return (
    <div className="table-wrap">
      <table className={`rv-cards${className ? ` ${className}` : ""}`} {...rest}>
        {caption && <caption className="rv-cards-caption">{caption}</caption>}
        {children}
      </table>
    </div>
  );
}

type CardCellProps = TdHTMLAttributes<HTMLTableCellElement> & {
  /** Visible label used when the cell becomes a card row. Pass "" for icon/action cells. */
  label: string;
  /** Let the cell occupy the full width of the card. */
  wide?: boolean;
};

/** Cell with the label the card layout needs. Keeps ordinary table semantics on desktop. */
export function CardCell({ label, wide, children, ...rest }: CardCellProps) {
  return (
    <td data-label={label} data-span={wide ? "all" : undefined} {...rest}>
      {children}
    </td>
  );
}
