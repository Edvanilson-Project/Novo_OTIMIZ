import { Injectable } from '@nestjs/common';
import { DataSource } from 'typeorm';
import { BaseRepository } from '../../../common/repositories/base.repository';
import { Trip } from '../entities/trip.entity';
import { Driver } from '../entities/driver.entity';

@Injectable()
export class TripRepository extends BaseRepository<Trip> {
  constructor(private dataSource: DataSource) {
    super(Trip, dataSource.createEntityManager());
  }
}

@Injectable()
export class DriverRepository extends BaseRepository<Driver> {
  constructor(private dataSource: DataSource) {
    super(Driver, dataSource.createEntityManager());
  }
}
