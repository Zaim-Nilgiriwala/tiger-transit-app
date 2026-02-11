import React, { useState } from 'react';
import { StyleSheet, View, Text, ScrollView, Switch, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Typography, Radius, Shadows, Spacing } from '../theme';

interface SettingRowProps {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  value?: string;
  isToggle?: boolean;
  toggleValue?: boolean;
  onToggle?: (val: boolean) => void;
  onPress?: () => void;
}

const SettingRow: React.FC<SettingRowProps> = ({ icon, label, value, isToggle, toggleValue, onToggle, onPress }) => {
  const content = (
    <View style={styles.settingRow}>
      <Ionicons name={icon} size={20} color={Colors.textSecondary} style={styles.settingIcon} />
      <Text style={styles.settingLabel}>{label}</Text>
      {isToggle ? (
        <Switch
          value={toggleValue}
          onValueChange={onToggle}
          trackColor={{ false: Colors.gray300, true: Colors.orangeLight }}
          thumbColor={toggleValue ? Colors.orange : Colors.gray100}
        />
      ) : (
        <View style={styles.settingRight}>
          {value && <Text style={styles.settingValue}>{value}</Text>}
          <Ionicons name="chevron-forward" size={16} color={Colors.gray400} />
        </View>
      )}
    </View>
  );

  if (onPress && !isToggle) {
    return <TouchableOpacity onPress={onPress} activeOpacity={0.6}>{content}</TouchableOpacity>;
  }

  return content;
};

const SettingsScreen: React.FC = () => {
  const [showNotifications, setShowNotifications] = useState(true);
  const [showDelayAlerts, setShowDelayAlerts] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);

  return (
    <ScrollView style={styles.container}>
      {/* Preferences */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Preferences</Text>
        <View style={styles.sectionCard}>
          <SettingRow
            icon="refresh-outline"
            label="Auto-refresh data"
            isToggle
            toggleValue={autoRefresh}
            onToggle={setAutoRefresh}
          />
          <View style={styles.divider} />
          <SettingRow
            icon="map-outline"
            label="Default map style"
            value="Standard"
          />
          <View style={styles.divider} />
          <SettingRow
            icon="location-outline"
            label="Distance units"
            value="Miles"
          />
        </View>
      </View>

      {/* Notifications */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Notifications</Text>
        <View style={styles.sectionCard}>
          <SettingRow
            icon="notifications-outline"
            label="Push notifications"
            isToggle
            toggleValue={showNotifications}
            onToggle={setShowNotifications}
          />
          <View style={styles.divider} />
          <SettingRow
            icon="alert-circle-outline"
            label="Delay alerts"
            isToggle
            toggleValue={showDelayAlerts}
            onToggle={setShowDelayAlerts}
          />
        </View>
      </View>

      {/* About */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>About</Text>
        <View style={styles.sectionCard}>
          <SettingRow
            icon="information-circle-outline"
            label="Version"
            value="1.0.0"
          />
          <View style={styles.divider} />
          <SettingRow
            icon="school-outline"
            label="Auburn University"
            value="Tiger Transit"
          />
        </View>
      </View>

      {/* Legal */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Legal</Text>
        <View style={styles.sectionCard}>
          <SettingRow
            icon="document-text-outline"
            label="Terms of Service"
          />
          <View style={styles.divider} />
          <SettingRow
            icon="shield-checkmark-outline"
            label="Privacy Policy"
          />
          <View style={styles.divider} />
          <SettingRow
            icon="code-slash-outline"
            label="Open Source Licenses"
          />
        </View>
      </View>

      <View style={styles.footer} />
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  section: {
    marginTop: Spacing.xl,
    paddingHorizontal: Spacing.lg,
  },
  sectionTitle: {
    fontSize: Typography.size.sm,
    fontWeight: Typography.weight.semibold,
    color: Colors.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: Spacing.sm,
    marginLeft: Spacing.xs,
  },
  sectionCard: {
    backgroundColor: Colors.surface,
    borderRadius: Radius.lg,
    ...Shadows.sm,
  },
  settingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 56,
    paddingHorizontal: Spacing.lg,
  },
  settingIcon: {
    marginRight: Spacing.md,
  },
  settingLabel: {
    flex: 1,
    fontSize: Typography.size.md,
    color: Colors.textPrimary,
  },
  settingRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
  },
  settingValue: {
    fontSize: Typography.size.md,
    color: Colors.textTertiary,
  },
  divider: {
    height: 1,
    backgroundColor: Colors.border,
    marginLeft: 52,
  },
  footer: {
    height: Spacing['3xl'],
  },
});

export default SettingsScreen;
