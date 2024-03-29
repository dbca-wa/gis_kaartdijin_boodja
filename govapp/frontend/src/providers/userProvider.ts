import { BackendService } from "../backend/backend.service";
import { BackendServiceStub } from "../backend/backend.stub";
import { RawCustodian, RawUser, RawUserFilter, User } from "../backend/backend.api";
import { Custodian, UserFilter } from "./userProvider.api";

export class UserProvider {
  // Get the backend stub if the test flag is used.
  private backend: BackendService = import.meta.env.MODE === "mock" ? new BackendServiceStub() : new BackendService();
  // Load all users; they're used for the select inputs
  public users = this.fetchUsers();
  public custodians = this.fetchCustodians();
  public me = this.fetchMe();
  public groups = this.fetchGroups();


  private async rawToUser ({ id, username, groups }: RawUser): Promise<User> {
    const providerGroups = await userProvider.groups;
    return {
      id,
      username,
      groups: groups.map(groupId => providerGroups.find(group => group.id === groupId))
    } as User;
  }

  public rawToCustodian (rawCustodian: RawCustodian): Custodian {
    return {
      id: rawCustodian.id,
      name: rawCustodian.name,
      contactName: rawCustodian.contact_name,
      contactEmail: rawCustodian.contact_email,
      contactPhone: rawCustodian.contact_phone
    };
  }

  public async fetchUser (userId: number): Promise<User> {
    return this.rawToUser(await this.backend.getUser(userId));
  }

  public async fetchUsers ({ ids, usernames }: UserFilter = {}): Promise<User[]> {
    const filters = {
      id__in: ids,
      username__in: usernames
    } as RawUserFilter;

    const users = await this.backend.getUsers(filters);
    return await Promise.all(users.results.map(user => this.rawToUser(user)));
  }

  public async fetchCustodian (id: number): Promise<Custodian> {
    return this.rawToCustodian(await this.backend.getRawCustodian(id));
  }

  public async fetchCustodians (): Promise<Custodian[]> {
    const rawCustodians = await this.backend.getRawCustodians();
    return rawCustodians.results.map(this.rawToCustodian);
  }

  public async fetchMe () {
    return this.rawToUser(await this.backend.getMe());
  }

  public async fetchGroups () {
    return (await this.backend.getGroups()).results;
  }

  // We don't need to paginate here so unwrap the results
  public static getUserFromId (userId: number | undefined, users: Array<User>): User | undefined {
    return userId !== null ? users.find(user => user.id === userId) : undefined;
  }

  public static getUniqueUsers (userObjects: Array<User>): Array<User> {
    return userObjects
      .reduce((previous, current) => {
        return current && previous.findIndex(value => value.id === current.id) === -1 ? [...previous, current] : previous;
      }, [] as Array<User>);
  }

  /**
   * Get list of unique `User` ids across multiple fields
   * @param userObjectList - An array of object containing column values e.g. `[{ custodian: 4, assignedTo: 5 }]`
   */
  public static getUniqueUserIds (userObjectList: Array<Record<string, number | undefined>>) {
    // Extract all keys and remove dupes
    return userObjectList
      .map(userObject => Array.from(Object.values(userObject)))
      .flat()
      .filter((value, index, self) => {
        return value !== null && self.indexOf(value) === index;
      }) as Array<number>;
  }
}

export const userProvider = new UserProvider();