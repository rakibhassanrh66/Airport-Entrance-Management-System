package airport.entrance.management;

import java.util.List;

public class ViewEntries {
    public void execute(List<Person> persons) {
        if (persons.isEmpty()) {
            System.out.println("No entries stored yet.");
            return;
        }

        System.out.println("Stored Entries:");
        for (Person person : persons) {
            System.out.println("Name: " + person.getName()
                    + ", ID: " + person.getId()
                    + ", Contact number: " + person.getNum());
        }
    }
}
