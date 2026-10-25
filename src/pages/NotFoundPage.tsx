import { Compass } from "lucide-react";
import { Button, EmptyState } from "../components/ui";
import { navigate, useLocation } from "../lib/router";

export default function NotFoundPage() {
  const { path } = useLocation();
  return <EmptyState icon={Compass} title="Page not found" detail={<>No workspace exists at <code>{path}</code>.</>} action={<Button variant="primary" onClick={() => navigate("/")}>Go to the overview</Button>} />;
}
