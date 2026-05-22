import { Entity, Column, ManyToOne, JoinColumn } from 'typeorm';
import { Company } from './company.entity';
import { TenantBaseEntity } from '../../../common/entities/base.entity';

export enum UserRole {
  SUPER_ADMIN = 'super_admin',
  COMPANY_ADMIN = 'company_admin',
  ANALYST = 'analyst',
  OPERATOR = 'operator',
}

@Entity('users')
export class User extends TenantBaseEntity {
  @Column({ unique: true })
  email: string;

  @Column({ select: false })
  passwordHash: string;

  @Column()
  name: string;

  @Column({ type: 'enum', enum: UserRole, default: UserRole.OPERATOR })
  role: UserRole;

  @Column({ default: true })
  isActive: boolean;

  @Column({ nullable: true })
  lastLoginAt: Date;

  @Column({ nullable: true, select: false })
  refreshTokenHash: string | null;

  @Column({ nullable: true, select: false })
  refreshTokenExpiresAt: Date | null;

  @ManyToOne(() => Company)
  @JoinColumn({ name: 'companyId' })
  company: Company;
}
