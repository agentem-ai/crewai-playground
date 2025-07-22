import * as React from "react";
import { X } from "lucide-react";
import { cn } from "../../lib/utils";

interface SheetProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  children: React.ReactNode;
}

interface SheetContentProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  side?: "left" | "right" | "top" | "bottom";
}

const Sheet: React.FC<SheetProps> = ({ open, onOpenChange, children }) => {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      <div 
        className="fixed inset-0 bg-black/40 backdrop-blur-sm transition-all duration-100 data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in" 
        onClick={() => onOpenChange?.(false)}
      />
      <div className="relative z-50">
        {children}
      </div>
    </div>
  );
};

const SheetTrigger: React.FC<{ children: React.ReactNode; onClick?: () => void }> = ({ 
  children, 
  onClick 
}) => {
  return (
    <div onClick={onClick}>
      {children}
    </div>
  );
};

const SheetContent: React.FC<SheetContentProps> = ({ 
  className, 
  children,
  side = "right",
  ...props 
}) => {
  const sideStyles = {
    right: "ml-auto animate-slide-in-from-right",
    left: "mr-auto animate-slide-in-from-left",
    top: "mb-auto animate-slide-in-from-top",
    bottom: "mt-auto animate-slide-in-from-bottom",
  };

  return (
    <div
      className={cn(
        "fixed z-50 bg-background shadow-lg border overflow-auto",
        side === "right" && "inset-y-0 right-0 w-3/4 max-w-3xl",
        side === "left" && "inset-y-0 left-0 w-3/4 max-w-3xl",
        side === "top" && "inset-x-0 top-0 h-3/4",
        side === "bottom" && "inset-x-0 bottom-0 h-3/4",
        sideStyles[side],
        className
      )}
      {...props}
    >
      <div className="p-6 h-full flex flex-col">
        {children}
      </div>
    </div>
  );
};

const SheetHeader: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({
  className,
  ...props
}) => (
  <div
    className={cn(
      "flex flex-col space-y-2 text-center sm:text-left mb-6",
      className
    )}
    {...props}
  />
);

const SheetTitle: React.FC<React.HTMLAttributes<HTMLHeadingElement>> = ({
  className,
  ...props
}) => (
  <h3
    className={cn(
      "text-lg font-semibold text-foreground",
      className
    )}
    {...props}
  />
);

const SheetDescription: React.FC<React.HTMLAttributes<HTMLParagraphElement>> = ({
  className,
  ...props
}) => (
  <p
    className={cn(
      "text-sm text-muted-foreground",
      className
    )}
    {...props}
  />
);

const SheetClose: React.FC<{ onClick?: () => void }> = ({ onClick }) => (
  <button
    className="absolute top-4 right-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-secondary"
    onClick={onClick}
  >
    <X className="h-4 w-4" />
    <span className="sr-only">Close</span>
  </button>
);

export {
  Sheet,
  SheetTrigger,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetClose,
};
