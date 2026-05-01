import re

with open("frontend/src/app/(DashboardLayout)/operations/_types.ts", "r") as f:
    content = f.read()

types_to_insert = """

export interface OptimizationDutyTimeSegment {
  type?: string;
  event_type?: string;
  event_scope?: string;
  start?: number;
  end?: number;
  duration?: number;
  duration_minutes?: number;
  event_label?: string;
  is_work_time?: boolean;
  is_driving_time?: boolean;
  is_idle_time?: boolean;
  is_normal_break?: boolean;
  is_mandatory_rest?: boolean;
  is_pullout?: boolean;
  is_pullback?: boolean;
  rest_valid?: boolean;
  rule_code?: string;
  violation_code?: string;
  explanation?: string;
  trip_ids?: number[];
  block_id?: number | string;
  location?: number | string;
  location_start?: number | string;
  location_end?: number | string;
}

export interface OptimizationOperationalTimeReport {
  duty_start?: number;
  duty_end?: number;
  spread_time?: number;
  window_time?: number;
  work_time?: number;
  driving_time?: number;
  idle_time?: number;
  normal_break_time?: number;
  mandatory_rest_time?: number;
  pullout_time?: number;
  pullback_time?: number;
  mandatory_rest?: {
    mandatory_rest_required?: boolean;
    has_valid_mandatory_rest?: boolean;
    violations?: string[];
  };
  operator?: {
    operator_not_assigned?: boolean;
  };
}
"""

if "OptimizationDutyTimeSegment" not in content:
    content = content.replace("export interface OptimizationDuty {", types_to_insert + "\nexport interface OptimizationDuty {")
    content = content.replace("  segments?: OptimizationDutySegment[];", "  segments?: OptimizationDutySegment[];\n  duty_time_segments?: OptimizationDutyTimeSegment[];\n  operational_time_report?: OptimizationOperationalTimeReport;")
    
    with open("frontend/src/app/(DashboardLayout)/operations/_types.ts", "w") as f:
        f.write(content)
    print("Patched types.")
else:
    print("Already patched types.")
