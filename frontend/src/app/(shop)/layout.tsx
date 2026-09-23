import { NovaLauncher } from "@/components/genora/nova-launcher";
import { SiteFooter, SiteHeader } from "@/components/layout/site-header";

export default function ShopLayout({ children }: LayoutProps<"/">) {
  return (
    <>
      <SiteHeader />
      <main className="flex-1">{children}</main>
      <SiteFooter />
      <NovaLauncher />
    </>
  );
}
