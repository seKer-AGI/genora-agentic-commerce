import Link from "next/link";

import { Logo } from "@/components/layout/site-header";

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-2">
      <div className="flex flex-col px-4 py-6 sm:px-10">
        <Logo />
        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-sm">{children}</div>
        </div>
        <p className="text-center text-xs text-muted-foreground">
          <Link href="/" className="hover:underline">Back to the marketplace</Link>
        </p>
      </div>
      <div className="bg-genora relative hidden overflow-hidden lg:block">
        <div className="absolute inset-0 flex flex-col justify-end p-12 text-white">
          <p className="text-3xl font-semibold leading-tight">“Find me a laptop under $1000 for programming.”</p>
          <p className="mt-3 max-w-md text-white/80">
            GenOra Nova understands what you need, searches thousands of listings, compares them honestly and only acts
            after you confirm.
          </p>
        </div>
      </div>
    </div>
  );
}
