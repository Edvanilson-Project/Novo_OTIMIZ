import 'reflect-metadata';
import { DataSource } from 'typeorm';
import { seedVehiclesData } from './vehicle-types-and-vehicles.seed';

const AppDataSource = new DataSource({
  type: 'postgres',
  host: process.env.DB_HOST || 'localhost',
  port: parseInt(process.env.DB_PORT || '5432'),
  username: process.env.DB_USER || 'postgres',
  password: process.env.DB_PASSWORD || 'postgres',
  database: process.env.DB_NAME || 'otimiz_db',
  entities: [__dirname + '/../../modules/database/entities/**/*.entity.ts'],
  synchronize: true,
  logging: true,
});

async function runSeeds() {
  try {
    await AppDataSource.initialize();
    console.log('Database connected');

    await seedVehiclesData(AppDataSource);

    console.log('All seeds completed successfully');
    process.exit(0);
  } catch (error) {
    console.error('Error running seeds:', error);
    process.exit(1);
  }
}

void runSeeds();
