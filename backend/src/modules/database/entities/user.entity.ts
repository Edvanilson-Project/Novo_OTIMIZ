import { Entity, Column, ManyToOne, JoinColumn } from 'typeorm';
import { Company } from './company.entity';
import { TenantBaseEntity } from '../../../common/entities/base.entity';

@Entity('users')
export class User extends TenantBaseEntity {
  @Column({ unique: true })
  email: string;

  @Column({ select: false })
  passwordHash: string;

  @Column()
  name: string;

  @Column({ default: 'operator' })
  role: string;

  @Column({ default: true })
  isActive: boolean;

  @Column({ nullable: true })
  lastLoginAt: Date;

  @ManyToOne(() => Company)
  @JoinColumn({ name: 'companyId' })
  company: Company;
}
