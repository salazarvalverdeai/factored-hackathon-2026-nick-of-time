"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export interface ChartPoint {
  label: string;
  value: number;
}

/**
 * Bar chart in a card (Recharts). Every figure on a chart needs a label for its origin ([data] [simulated] …):
 * pass it in `source`, it is printed under the title.
 */
export function BarChartCard({
  title,
  source,
  data,
  height = 220,
}: {
  title: string;
  source: string;
  data: ChartPoint[];
  height?: number;
}) {
  return (
    <Card data-slot="chart-card">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{source}</CardDescription>
      </CardHeader>
      <CardContent>
        <div style={{ height }} role="img" aria-label={`${title}: ${data.map((d) => `${d.label} ${d.value}`).join(", ")}`}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="currentColor" opacity={0.15} />
              <XAxis dataKey="label" tickLine={false} axisLine={false} fontSize={12} />
              <YAxis tickLine={false} axisLine={false} fontSize={12} />
              <Tooltip cursor={{ fill: "currentColor", opacity: 0.08 }} />
              <Bar dataKey="value" fill="var(--chart-1, currentColor)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
