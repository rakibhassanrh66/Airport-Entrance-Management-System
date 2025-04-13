package airport.entrance.management;

import java.util.List;

public class ViewEntries {
    public void execute(List<Person> persons) {
        System.out.println("Stored Entries:");
        for (Person person : persons) {
            System.out.println("Name: " + person.getName() + ", ID: " + person.getId() + ",Contuct number : " + person.getNum());
        }
    }
}
